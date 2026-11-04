"""
Module Import & Architecture Smoke Tests — Verifies all 4 tiers, future stubs,
and thin `app.py` orchestrator import cleanly with zero circular dependencies.
"""

import os
import unittest


class TestModularArchitectureImports(unittest.TestCase):
    def test_all_tiers_and_app_import_cleanly(self) -> None:
        import app
        import src.config
        import src.infrastructure
        import src.providers
        import src.providers.eod_sync_service
        import src.layers
        import src.layers.future.layer2_sector
        import src.layers.future.layer3_vcp
        import src.layers.future.layer4_entry
        import src.layers.future.layer5_risk
        import src.ui

        self.assertTrue(callable(app.main))
        self.assertTrue(callable(src.providers.eod_sync_service.refresh_daily_market_data))
        self.assertTrue(callable(src.layers.run_screening_pipeline))

    def test_legacy_flat_files_removed_and_no_local_data_folder(self) -> None:
        legacy_paths = [
            "src/config.py",
            "src/data_pipeline.py",
            "src/screener_engine.py",
            "src/storage.py",
            "src/supabase_client.py",
            "data",
        ]
        for rel in legacy_paths:
            self.assertFalse(os.path.exists(rel), f"Legacy path should not exist: {rel}")


if __name__ == "__main__":
    unittest.main()
