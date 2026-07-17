"""
Stage 3 (targeted focus) for CSV: decide, per column, WHY values are missing before
choosing a repair strategy. This is the thing naive answers skip — "fill with the
mean" silently injects bias when the missingness is MNAR (e.g. a clinical field
that's blank precisely because the true value is the template's default/negative
case, not because of a random sensor dropout).

- MCAR (Missing Completely At Random): null-rate is statistically independent of
  every other observed column -> safe to auto-impute (mean/mode).
- MAR (Missing At Random): null-rate is explained by another OBSERVED column
  (e.g. "smoking_status" is null only for pediatric records) -> safe to
  cross-file backfill using that relationship, never a blind average.
- MNAR (Missing Not At Random): neither test above resolves it -> the missingness
  likely depends on the UNOBSERVED value itself -> never guess, flag for HITL.
"""
import pandas as pd
from scipy.stats import chi2_contingency, ttest_ind

ALPHA = 0.05
NUMERIC_MEAN_GAP_FACTOR = 0.5  # how many std-devs apart present/missing means must be to count as "explained"
MAR_HIGH_NULL_RATE = 0.9
MAR_LOW_NULL_RATE = 0.1
MIN_GROUP_SIZE = 5


class MissingnessClassifier:
    def __init__(self, domain_priors: dict[str, str] | None = None):
        """
        domain_priors: column_name -> forced classification ('MNAR', typically).

        Why this exists: MNAR is defined as "missingness that depends on the
        unobserved value itself." If the variable it truly depends on isn't a
        column in this dataset, its null pattern looks statistically identical
        to MCAR -- independent of everything you *can* measure. No amount of
        chi-square/t-test rigor can tell them apart from the data alone; that's
        the textbook limitation of Little's-test-style MCAR diagnostics. A
        staff-level answer accounts for this by naming known-risky fields up
        front from domain knowledge (e.g. "smoking_status" in a clinical
        template that silently skips it for non-smokers) rather than trusting
        the statistical test to catch every case.
        """
        self.domain_priors = domain_priors or {}

    def classify(self, df: pd.DataFrame, column: str, other_columns: list[str]) -> tuple[str, str | None]:
        """Returns (missingness_class, explaining_column_or_None)."""
        null_mask = df[column].isna()
        if null_mask.sum() == 0:
            return "NONE", None

        explaining_column = self._find_explaining_column(null_mask, df, other_columns)
        if explaining_column:
            return "MAR", explaining_column

        if column in self.domain_priors:
            return self.domain_priors[column], None

        if self._is_independent_of_other_columns(null_mask, df, other_columns):
            return "MCAR", None

        return "MNAR", None

    def strategy_for(self, missingness_class: str) -> str:
        return {
            "MCAR": "auto_impute",
            "MAR": "cross_file_backfill",
            "MNAR": "flag_for_hitl",
            "NONE": "skip",
        }[missingness_class]

    # -- internals --------------------------------------------------------

    def _find_explaining_column(self, null_mask: pd.Series, df: pd.DataFrame, other_columns: list[str]) -> str | None:
        for col in other_columns:
            other = df[col]
            if other.isna().all():
                continue

            if pd.api.types.is_numeric_dtype(other):
                present = other[~null_mask].dropna()
                missing = other[null_mask].dropna()
                if len(present) < MIN_GROUP_SIZE or len(missing) < MIN_GROUP_SIZE:
                    continue
                _, p_value = ttest_ind(present, missing, equal_var=False)
                mean_gap = abs(present.mean() - missing.mean())
                if p_value < ALPHA and mean_gap > present.std() * NUMERIC_MEAN_GAP_FACTOR:
                    return col
            else:
                contingency = pd.crosstab(other.fillna("__NA__"), null_mask)
                if contingency.shape[0] < 2 or True not in contingency.columns:
                    continue
                null_rate_by_category = contingency[True] / contingency.sum(axis=1)
                # A category that's almost-always-null next to one that's almost-never-null
                # is the textbook MAR signal (e.g. all pediatric rows skip "smoking_status").
                if (null_rate_by_category > MAR_HIGH_NULL_RATE).any() and (null_rate_by_category < MAR_LOW_NULL_RATE).any():
                    return col
        return None

    def _is_independent_of_other_columns(self, null_mask: pd.Series, df: pd.DataFrame, other_columns: list[str]) -> bool:
        for col in other_columns:
            other = df[col]
            if pd.api.types.is_numeric_dtype(other):
                present = other[~null_mask].dropna()
                missing = other[null_mask].dropna()
                if len(present) < MIN_GROUP_SIZE or len(missing) < MIN_GROUP_SIZE:
                    continue
                _, p_value = ttest_ind(present, missing, equal_var=False)
                if p_value < ALPHA:
                    return False
            else:
                contingency = pd.crosstab(other.fillna("__NA__"), null_mask)
                if contingency.shape[0] < 2 or contingency.shape[1] < 2:
                    continue
                _, p_value, _, _ = chi2_contingency(contingency)
                if p_value < ALPHA:
                    return False
        return True
