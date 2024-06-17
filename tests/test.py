from sparql_grammar_pydantic import *
from sparql_grammar_pydantic.grammar import IRIREF

test = IRIREF(value="^")
print('t')
# from pydantic import BaseModel, StringConstraints
# from typing import Annotated
#
# # Define the pattern using the Unicode range
# PATTERN = r"[\u0300-\u036F]"
#
#
# # Create a model with a field using the pattern
# class TestModel(BaseModel):
#     part_1: Annotated[str, StringConstraints(pattern=PATTERN)]
#
#
# # Testing the model with valid and invalid inputs
# try:
#     # Valid input: a character in the range [\u0300-\u036F]
#     valid_example_1 = TestModel(part_1="\u0300")  # Combining Grave Accent
#     valid_example_2 = TestModel(part_1="\u0301")  # Combining Acute Accent
#     valid_example_3 = TestModel(part_1="\u0302")  # Combining Circumflex Accent
#     print("Valid examples passed:")
#     print(valid_example_1)
#     print(valid_example_2)
#     print(valid_example_3)
#
#     # Invalid input: a character outside the range [\u0300-\u036F]
#     invalid_example = TestModel(part_1="a")
#     print("Invalid example passed:", invalid_example)
# except ValueError as e:
#     print("Validation error:", e)
