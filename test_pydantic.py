from pydantic import BaseModel, ValidationError
from typing import List

class UserOut(BaseModel):
    id: int

class PRSchema(BaseModel):
    id: int
    user: UserOut

class Resp(BaseModel):
    items: List[PRSchema]

try:
    Resp(items=[{"id": 1, "user": {"id": "str_not_int"}}])
except ValidationError as e:
    print("TEST 1 - nested id error:")
    print(e)
    
try:
    Resp(items=[{"id": "str_not_int", "user": {"id": 1}}])
except ValidationError as e:
    print("\nTEST 2 - top level id error:")
    print(e)
