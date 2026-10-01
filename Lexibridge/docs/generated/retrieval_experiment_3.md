# Retrieval Experiment Report

- course_id: 1
- kb_version_id: 18
- recommendation: Keep lexical. No tested backend improved top1 accuracy.

## Metrics
### lexical
```json
{
  "backend": "lexical",
  "case_count": 21,
  "top1_accuracy": 0.0,
  "top3_accuracy": 0.0,
  "top5_accuracy": 0.0,
  "negative_match_error_rate": 0.0,
  "no_evidence_forced_match_rate": 0.0,
  "mean_reciprocal_rank": 0.0,
  "average_latency_ms": 10.12,
  "empty_result_rate": 0.8095,
  "restricted_source_violation_count": 0,
  "personal_leakage_count": 0,
  "details": [
    {
      "query": "Hash Table",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Collision Resolution",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Binary Search Tree",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Stack",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Linked List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Graph",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Depth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Breadth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Time Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Space Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Heap",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Priority Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Recursion",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Dynamic Programming",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Greedy Algorithm",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Balanced Tree",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency Matrix",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Topological Sort",
      "result_count": 0,
      "expected_rank": 0
    }
  ]
}
```
### vector
```json
{
  "backend": "vector",
  "case_count": 21,
  "top1_accuracy": 0.0,
  "top3_accuracy": 0.0,
  "top5_accuracy": 0.0,
  "negative_match_error_rate": 0.0,
  "no_evidence_forced_match_rate": 0.0,
  "mean_reciprocal_rank": 0.0,
  "average_latency_ms": 10.91,
  "empty_result_rate": 0.8095,
  "restricted_source_violation_count": 0,
  "personal_leakage_count": 0,
  "details": [
    {
      "query": "Hash Table",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Collision Resolution",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Binary Search Tree",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Stack",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Linked List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Graph",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Depth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Breadth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Time Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Space Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Heap",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Priority Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Recursion",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Dynamic Programming",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Greedy Algorithm",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Balanced Tree",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency Matrix",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Topological Sort",
      "result_count": 0,
      "expected_rank": 0
    }
  ]
}
```
### hybrid
```json
{
  "backend": "hybrid",
  "case_count": 21,
  "top1_accuracy": 0.0,
  "top3_accuracy": 0.0,
  "top5_accuracy": 0.0,
  "negative_match_error_rate": 0.0,
  "no_evidence_forced_match_rate": 0.0,
  "mean_reciprocal_rank": 0.0,
  "average_latency_ms": 20.24,
  "empty_result_rate": 0.8095,
  "restricted_source_violation_count": 0,
  "personal_leakage_count": 0,
  "details": [
    {
      "query": "Hash Table",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Collision Resolution",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Binary Search Tree",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Stack",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Linked List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Graph",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Depth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Breadth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Time Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Space Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Heap",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Priority Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Recursion",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Dynamic Programming",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Greedy Algorithm",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Balanced Tree",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency Matrix",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Topological Sort",
      "result_count": 0,
      "expected_rank": 0
    }
  ]
}
```
### hybrid_rerank
```json
{
  "backend": "hybrid_rerank",
  "case_count": 21,
  "top1_accuracy": 0.0,
  "top3_accuracy": 0.0,
  "top5_accuracy": 0.0,
  "negative_match_error_rate": 0.0,
  "no_evidence_forced_match_rate": 0.0,
  "mean_reciprocal_rank": 0.0,
  "average_latency_ms": 20.06,
  "empty_result_rate": 0.8095,
  "restricted_source_violation_count": 0,
  "personal_leakage_count": 0,
  "details": [
    {
      "query": "Hash Table",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Collision Resolution",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Binary Search Tree",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Stack",
      "result_count": 1,
      "expected_rank": 0
    },
    {
      "query": "Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Linked List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Graph",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Depth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Breadth-first Search",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Time Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Space Complexity",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Heap",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Priority Queue",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Recursion",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Dynamic Programming",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Greedy Algorithm",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Balanced Tree",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency List",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Adjacency Matrix",
      "result_count": 0,
      "expected_rank": 0
    },
    {
      "query": "Topological Sort",
      "result_count": 0,
      "expected_rank": 0
    }
  ]
}
```
