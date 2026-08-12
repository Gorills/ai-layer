"""Small persisted-version constants for scanner/index compatibility."""

CONTENT_IDENTITY_VERSION = 2
# v5 keeps raw source out of semantic memory while adding a dedicated metadata-only
# Project Map (paths, symbols, imports and compact purposes) for cheap code navigation.
SCANNER_SCHEMA_VERSION = 5
