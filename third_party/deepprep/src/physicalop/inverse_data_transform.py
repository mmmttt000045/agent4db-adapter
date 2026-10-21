from ._base import BaseOp
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import re

@dataclass
class InversePivot(BaseOp):
    action_type: str = field(
        default="inverse_pivot",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_pivot"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    index: str = field(metadata={"help": 'index column'})
    columns: str = field(metadata={"help": 'columns that were pivoted'})
    values: str = field(metadata={"help": 'values that were aggregated'})
    aggfunc: str = field(metadata={"help": 'aggregation function that was used'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InversePivot Operator

* Signature: InversePivot(table_name="table_name", index="index_col", columns="pivot_col", values="value_col", aggfunc="mean")
* Description: Reverse a pivot operation to restore the original table structure.
* Example: InversePivot(table_name="my_table", index="date", columns="category", values="sales", aggfunc="sum")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InversePivot\(table_name=(.*?), index=(.*?), columns=(.*?), values=(.*?), aggfunc=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, index, columns, values, aggfunc = (item.strip().strip("'\"") for item in matches[-1])
            return cls(table_name=table_name, index=index, columns=columns, values=values, aggfunc=aggfunc)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", index="{self.index}", columns="{self.columns}", values="{self.values}", aggfunc="{self.aggfunc}")'

@dataclass
class InverseStack(BaseOp):
    action_type: str = field(
        default="inverse_stack",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_stack"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    id_vars: List[str] = field(metadata={"help": 'columns that were kept as identifiers'})
    value_vars: List[str] = field(metadata={"help": 'columns that were stacked'})
    var_name: str = field(default="variable", metadata={"help": 'name of the stacked variable column'})
    value_name: str = field(default="value", metadata={"help": 'name of the stacked value column'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseStack Operator

* Signature: InverseStack(table_name="table_name", id_vars=["id"], value_vars=["col1", "col2"], var_name="variable", value_name="value")
* Description: Reverse a stack operation to restore wide format from long format.
* Example: InverseStack(table_name="my_table", id_vars=["id"], value_vars=["jan", "feb", "mar"], var_name="month", value_name="sales")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseStack\(table_name=(.*?), id_vars=(.*?), value_vars=(.*?), var_name=(.*?), value_name=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, id_vars, value_vars, var_name, value_name = (item.strip().strip("'\"") for item in matches[-1])
            id_vars = eval(id_vars)
            value_vars = eval(value_vars)
            if isinstance(value_vars, list):
                value_vars = [str(v) for v in value_vars]
            if isinstance(id_vars, list):
                id_vars = [str(v) for v in id_vars]
            return cls(table_name=table_name, id_vars=id_vars, value_vars=value_vars, var_name=var_name, value_name=value_name)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", id_vars={self.id_vars}, value_vars={self.value_vars}, var_name="{self.var_name}", value_name="{self.value_name}")'

@dataclass
class InverseExplode(BaseOp):
    action_type: str = field(
        default="inverse_explode",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_explode"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    column: str = field(metadata={"help": 'column that was exploded'})
    split_comma: bool = field(default=False, metadata={"help": 'whether the original was split by comma'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseExplode Operator

* Signature: InverseExplode(table_name="table_name", column="col", split_comma=False)
* Description: Reverse an explode operation to combine values back into lists or comma-separated strings.
* Example: InverseExplode(table_name="my_table", column="tags", split_comma=True)
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseExplode\(table_name=(.*?), column=(.*?), split_comma=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, column, split_comma = (item.strip().strip("'\"") for item in matches[-1])
            return cls(table_name=table_name, column=column, split_comma=eval(split_comma))
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", column="{self.column}", split_comma={self.split_comma})'

@dataclass
class InverseWideToLong(BaseOp):
    action_type: str = field(
        default="inverse_wide_to_long",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_wide_to_long"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    subnames: List[str] = field(metadata={"help": 'prefix of columns that were converted'})
    i: List[str] = field(metadata={"help": 'columns used as identifiers'})
    j: str = field(default="variable", metadata={"help": 'name of the variable column'})
    sep: str = field(default="_", metadata={"help": 'separator used in column names'})
    suffix: str = field(default=r"\d+", metadata={"help": 'suffix pattern used in column names'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseWideToLong Operator

* Signature: InverseWideToLong(table_name="table_name", subnames=["col"], i=["id"], j="variable", sep="_", suffix="\d+")
* Description: Reverse a wide-to-long operation to convert long format data back to wide format.
* Example: InverseWideToLong(table_name="my_table", subnames=["value"], i=["id"], j="year", sep="_", suffix="\d+")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseWideToLong\(table_name=(.*?), subnames=(.*?), i=(.*?), j=(.*?), sep=(.*?), suffix=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, subnames, i, j, sep, suffix = (item.strip().strip("'\"") for item in matches[-1])
            subnames = eval(subnames)
            if isinstance(subnames, list):
                subnames = [str(s) for s in subnames]
            i = eval(i)
            if isinstance(i, list):
                i = [str(i) for i in i]
            return cls(table_name=table_name, subnames=subnames, i=i, j=j, sep=sep, suffix=suffix)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", subnames={self.subnames}, i={self.i}, j="{self.j}", sep="{self.sep}", suffix="{self.suffix}")'

@dataclass
class InverseTranspose(BaseOp):
    action_type: str = field(
        default="inverse_transpose",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_transpose"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseTranspose Operator

* Signature: InverseTranspose(table_name="table_name")
* Description: Reverse a transpose operation to restore original row-column structure.
* Example: InverseTranspose(table_name="my_table")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseTranspose\(table_name=(.*?)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name = matches[-1].strip().strip("'\"")
            return cls(table_name=table_name)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}")'

@dataclass
class InverseDropNulls(BaseOp):
    action_type: str = field(
        default="inverse_dropna",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_dropna"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    subset: Optional[List[str]] = field(default=None, metadata={"help": 'columns to consider for inserting null values'})
    how: str = field(default="any", metadata={"help": 'rule for inserting nulls: "all" for all subset values to be null, "any" for at least one to be null'})
    count: int = field(default=1, metadata={"help": 'number of rows to insert with null values'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseDropNulls Operator

* Signature: InverseDropNulls(table_name="table_name", subset=["col1", "col2"], how="any", count=1)
* Description: Insert rows with null values in specified columns based on the rule defined by 'how'.
* Example: InverseDropNulls(table_name="my_table", subset=["age", "salary"], how="all", count=2)
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseDropNulls\(table_name=(.*?), subset=(.*?), how=(.*?), count=(.*?)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, subset, how, count = (item.strip().strip("'\"") for item in matches[-1])
            subset_eval = eval(subset) if subset != "None" else None
            if isinstance(subset_eval, list):
                subset_eval = [str(s) for s in subset_eval]
            return cls(table_name=table_name, subset=subset_eval, how=how, count=int(count))
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", subset={self.subset}, how="{self.how}", count={self.count})'


@dataclass
class InverseDeduplicate(BaseOp):
    action_type: str = field(
        default="inverse_deduplicate",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_deduplicate"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    subset: Optional[List[str]] = field(default=None, metadata={"help": 'columns to check for inserting duplicate rows'})
    count: int = field(default=1, metadata={"help": 'number of duplicate rows to insert'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseDeduplicate Operator

* Signature: InverseDeduplicate(table_name="table_name", subset=["col1", "col2"], count=1)
* Description: Insert duplicate rows.
* Example: InverseDeduplicate(table_name="my_table", subset=["id"], count=1)
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseDeduplicate\(table_name=(.*?), subset=(.*?), count=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, subset, count = (item.strip().strip("'\"") for item in matches[-1])
            subset_eval = eval(subset) if subset != "None" else None
            if isinstance(subset_eval, list):
                subset_eval = [str(s) for s in subset_eval]
            return cls(table_name=table_name, subset=subset_eval, count=count)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", subset={self.subset}, count="{self.count}")'

class InverseMissingValueImputation(BaseOp):
    action_type: str = field(
        default="inverse_missing_value_imputation",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_missing_value_imputation"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    column: str = field(metadata={"help": 'column that was imputed'})
    mode: str = field(metadata={"help": 'mode of imputation'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseMissingValueImputation Operator

* Signature: InverseMissingValueImputation(table_name="table_name", column="col", mode="mean")
* Description: Reverse a missing value imputation operation to restore the original table structure.
* Example: InverseMissingValueImputation(table_name="my_table", column="age", mode="mean")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseMissingValueImputation\(table_name=(.*?), column=(.*?), mode=(.*)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, column, mode = (item.strip().strip("'\"") for item in matches[-1])
            return cls(table_name=table_name, column=column, mode=mode)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", column="{self.column}", mode="{self.mode}")'

class InverseOutlierDetection(BaseOp):
    action_type: str = field(
        default="inverse_outlier_detection",
        init=False,
        repr=False,
        metadata={"help": 'type of action, c.f., "inverse_outlier_detection"'}
    )
    table_name: str = field(metadata={"help": 'name of the table to apply the operation on'})
    column: str = field(metadata={"help": 'column that was detected'})

    @classmethod
    def get_action_description(cls) -> str:
        return """
## InverseOutlierDetection Operator

* Signature: InverseOutlierDetection(table_name="table_name", column="col")
* Description: Reverse an outlier detection operation to restore the original table structure.
* Example: InverseOutlierDetection(table_name="my_table", column="age")
"""

    @classmethod
    def parse_action_from_text(cls, text: str) -> Optional[BaseOp]:
        pattern = r'InverseOutlierDetection\(table_name=(.*?), column=(.*?)\)'
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if matches:
            table_name, column = (item.strip().strip("'\"") for item in matches[-1])
            return cls(table_name=table_name, column=column)
        return None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(table_name="{self.table_name}", column="{self.column}")'