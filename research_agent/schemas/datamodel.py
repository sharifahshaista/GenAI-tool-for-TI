from pydantic import BaseModel, Field, HttpUrl, field_validator, ValidationError
from typing import Any, Dict , Optional, List
from datetime import datetime
from pathlib import Path
import json 


class ClarificationQuestion(BaseModel):
    """Single clarification Q&A pair"""
    question: str = Field(..., min_length=1)
    answer: str = Field(default="")

class ClarificationResponse(BaseModel):
    """Clarification session response"""
    original_query: str = Field(..., min_length=1)
    questions_and_answers: List[ClarificationQuestion] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_validator('questions_and_answers')
    @classmethod
    def validate_qa_limit(cls, v):
        if len(v) > 5:
            raise ValueError("Too many clarification questions (max 5)")
        return v


class SerpQueryRequest(BaseModel):
    """Request for generating SERP queries"""
    query: str = Field(..., min_length=1)
    clarifications: Optional[ClarificationResponse] = None
    max_queries: int = Field(default=20, ge=1, le=50)



class SearchResult(BaseModel):
    """Individual search result"""
    query: str = Field(..., min_length=1)
    results: Any  # Can be refined based on actual structure
    timestamp: datetime = Field(default_factory=datetime.now)
    result_count: Optional[int] = None

class SearchResultsCollection(BaseModel):
    """Collection of all search results"""
    results: Dict[str, SearchResult] = Field(default_factory=dict)
    total_queries: int = Field(default=0)
    timestamp: datetime = Field(default_factory=datetime.now)

    def add_result(self, query: str, results: Any):
        """Add a search result to the collection"""
        self.results[query] = SearchResult(query=query, results=results)
        self.total_queries = len(self.results)

    def to_file(self, path: Path):
        """Save results to JSON file"""
        data = {}
        for query, result in self.results.items():
            data[query] = result.results
        path.write_text(json.dumps(data, ensure_ascii=False, indent=4))


class ResearchResult(BaseModel):
    """Final research output with validation"""
    topic: str = Field(..., min_length=1, max_length=500, description="Research topic")
    research_content: str = Field(..., min_length=100, description="Detailed research content")
    key_points: List[str] = Field(..., min_items=1, max_items=20, description="Key points extracted")
    sources: List[str] = Field(..., min_items=1, description="Sources used for research")
    urls: List[str] = Field(..., min_items=1, description="URLs used for research")
    timestamp: datetime = Field(default_factory=datetime.now)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in results")

    @field_validator('key_points')
    @classmethod
    def validate_key_points(cls, v):
        # Remove empty strings
        cleaned = [point for point in v if point and point.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty key point required")
        return cleaned

    @field_validator('sources')
    @classmethod
    def validate_sources(cls, v):
        # Ensure sources are not empty
        if not any(source.strip() for source in v):
            raise ValueError("At least one valid source required")
        return v

#  Pydantic Models for Learnings
class LearningSource(BaseModel):
    """Source information for a learning"""
    url: str = Field(description="Exact URL from the search results")
    title: Optional[str] = Field(default=None, description="Title of the source")
    

# class Learning(BaseModel):
#     """Individual learning with sources"""
#     id: int = Field(description="Learning number")
#     content: str = Field(description="The learning content")
#     entities: List[str] = Field(default_factory=list, description="Entities mentioned (people, places, companies)")
#     metrics: List[str] = Field(default_factory=list, description="Numbers, dates, percentages mentioned")
#     sources: List[LearningSource] = Field(description="Source URLs for this learning")
    

class QueryLearnings(BaseModel):
    """All learnings for a specific query"""
    query: str = Field(description="The SERP query")
    learnings: str = Field(description="Detailed learnings from the content based on the web search")
    entities: List[str] = Field(default_factory=list, description="Entities mentioned (people, places, companies)")
    metrics: List[str] = Field(default_factory=list, description="Numbers, dates, percentages mentioned")

