"""
AGS (Agent Sandbox) VM Manager

Derived from xlang-ai/OSWorld under Apache-2.0.
Modified and redistributed by Agent Sandbox Cookbook as part of the OSWorld AGS overlay.
"""
import logging

from desktop_env.providers.base import VMManager

logger = logging.getLogger("desktopenv.providers.ags.AGSVMManager")
logger.setLevel(logging.INFO)


class AGSVMManager(VMManager):
    """
    VM Manager for AGS (Agent Sandbox) provider.
    Sandboxes are dynamically created, so most operations are no-ops.
    """

    def initialize_registry(self, **kwargs):
        pass

    def add_vm(self, vm_path, **kwargs):
        pass

    def delete_vm(self, vm_path, **kwargs):
        pass

    def occupy_vm(self, vm_path, pid, **kwargs):
        pass

    def list_free_vms(self, **kwargs):
        return []

    def check_and_clean(self, **kwargs):
        pass

    def get_vm_path(self, **kwargs):
        # For AGS, path_to_vm is the template name
        from desktop_env.providers.ags.config import AGS_TEMPLATE
        return AGS_TEMPLATE
