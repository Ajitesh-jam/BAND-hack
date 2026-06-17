"""A tiny self-contained LangGraph agent that analyzes a piece of text.

This is a plain LangGraph agent with NO Band integration — it exists so the
Band Orchestrator can convert it into a live Band agent on demand. The graph
runs three sequential nodes: word count -> sentiment -> summary.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

_POSITIVE = {"love", "great", "good", "awesome", "excellent", "happy", "works", "best"}
_NEGATIVE = {"hate", "bad", "terrible", "broken", "awful", "slow", "crash", "worst"}


class AnalysisState(TypedDict, total=False):
    text: str
    word_count: int
    sentiment: str
    summary: str


def count_words(state: AnalysisState) -> dict:
    text = state.get("text", "")
    return {"word_count": len(text.split())}


def detect_sentiment(state: AnalysisState) -> dict:
    words = {w.strip(".,!?").lower() for w in state.get("text", "").split()}
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    if pos > neg:
        sentiment = "positive"
    elif neg > pos:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {"sentiment": sentiment}


def summarize(state: AnalysisState) -> dict:
    word_count = state.get("word_count", 0)
    sentiment = state.get("sentiment", "neutral")
    return {"summary": f"{word_count} words, sentiment={sentiment}."}


def build_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("count", count_words)
    graph.add_node("sentiment", detect_sentiment)
    graph.add_node("summary", summarize)
    graph.set_entry_point("count")
    graph.add_edge("count", "sentiment")
    graph.add_edge("sentiment", "summary")
    graph.add_edge("summary", END)
    return graph.compile()


graph = build_graph()


def run(text: str) -> dict:
    """Analyze a piece of text and return word_count, sentiment, and summary."""
    return graph.invoke({"text": text})


if __name__ == "__main__":
    print(run("I love this product, it works great!"))
    print(run("This is terrible and broken, the worst."))
