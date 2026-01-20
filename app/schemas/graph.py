from pydantic import BaseModel, Field
from typing import Literal

class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""
    
    binary_score: Literal["yes", "no"] = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )