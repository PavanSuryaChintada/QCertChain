"""Route-facing repositories. Every function takes the request Scope (an RLS-bound connection + org id) and
is the ONLY place route code reaches the database. Org-owned reads go through org_domains / org_id-scoped
tables; the database's row-level security is the backstop if a predicate is ever forgotten.
"""
