"""Route registration modules for staged ``backend/app.py`` extraction.

Current staged modules cover teacher learning analytics, student Concept Card
learning routes, teacher Concept Card review routes, teacher-facing student
feedback queue/triage routes, read-only provider governance/preflight routes,
provider policy mutation routes, provider preflight execution routes, and the
thin alignment verification HTTP adapter route, admin alignment run listing,
legacy provider admin observability views, and legacy provider admin
configuration GET views, and the legacy provider admin healthcheck POST route.
The optional Student pilot module is a privacy-minimized measurement adapter
around the existing Personal Workspace flow; it is not a product workflow.
Remaining route domains still live in ``backend/app.py``.
"""
