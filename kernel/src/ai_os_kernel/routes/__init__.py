"""HTTP transport layer.

Routers here define request/response shapes only. Business logic never
lives in this package (System Architecture: "Business logic shall never
reside in the API Layer") — a router calls into a Kernel component and
returns its result.
"""
