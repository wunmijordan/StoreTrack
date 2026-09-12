"""Compatibility exports for tenant-scoped backup helpers.

The implementation lives in :mod:`core.services`, an existing tracked module,
so production backup routing does not depend on this newer helper file being
carried by an overlay-style deployment.
"""
from .services import tenant_backup_objects, tenant_backup_querysets

__all__ = ["tenant_backup_objects", "tenant_backup_querysets"]
