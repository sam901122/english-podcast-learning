from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.daily_update = (ROOT / ".github/workflows/daily-update.yml").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    def test_daily_update_runs_twice_on_release_days(self):
        self.assertIn('cron: "5 6,8 * * 2-6"', self.daily_update)
        self.assertIn('timezone: "Asia/Taipei"', self.daily_update)

    def test_daily_update_skips_commit_when_content_is_unchanged(self):
        self.assertIn('echo "updated=false"', self.daily_update)
        self.assertIn("if: steps.podcast.outputs.updated == 'true'", self.daily_update)

    def test_daily_update_leaves_pages_deployment_to_pages_workflow(self):
        for action in ("actions/configure-pages", "actions/upload-pages-artifact", "actions/deploy-pages"):
            with self.subTest(action=action):
                self.assertNotIn(action, self.daily_update)
                self.assertIn(action, self.pages)

    def test_pages_workflow_deploys_site_changes(self):
        self.assertIn('- "site/**"', self.pages)


if __name__ == "__main__":
    unittest.main()
