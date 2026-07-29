"""Packaging-only smoke test for Step 1 of ``platform_sdk_v1_scope.md``:
proves ``ai_os_sdk`` and its six stub subpackages import cleanly. No
Protocol, model, or error class exists yet, so there is nothing else to
test until step 2.
"""

import ai_os_sdk
import ai_os_sdk.contracts
import ai_os_sdk.errors
import ai_os_sdk.models
import ai_os_sdk.sdk
import ai_os_sdk.testing
import ai_os_sdk.utilities


def test_package_and_every_stub_subpackage_import_cleanly() -> None:
    for module in (
        ai_os_sdk,
        ai_os_sdk.contracts,
        ai_os_sdk.models,
        ai_os_sdk.errors,
        ai_os_sdk.sdk,
        ai_os_sdk.utilities,
        ai_os_sdk.testing,
    ):
        assert module.__doc__ is not None
