"""Tests for the `flask auth change-admin-password` CLI command."""
from models import User


class TestChangeAdminPassword:
    def _run(self, app, args, input=None):
        runner = app.test_cli_runner()
        return runner.invoke(args=["auth", "change-admin-password", *args], input=input)

    def test_changes_password_of_default_admin(self, app, admin_user):
        # testadmin is the configured ADMIN_USERNAME (see TestingConfig)
        result = self._run(app, ["--password", "brandnew"])

        assert result.exit_code == 0
        assert "updated" in result.output
        user = User.query.filter_by(username="testadmin").first()
        assert user.check_password("brandnew")
        assert not user.check_password("testpassword")

    def test_changes_password_of_explicit_username(self, app, admin_user):
        result = self._run(app, ["--username", "testadmin", "--password", "explicitpw"])

        assert result.exit_code == 0
        user = User.query.filter_by(username="testadmin").first()
        assert user.check_password("explicitpw")

    def test_unknown_user_fails_without_changing_anything(self, app, admin_user):
        result = self._run(app, ["--username", "ghost", "--password", "whatever"])

        assert result.exit_code != 0
        assert "does not exist" in result.output
        # existing admin password is untouched
        user = User.query.filter_by(username="testadmin").first()
        assert user.check_password("testpassword")

    def test_prompts_for_password_when_not_provided(self, app, admin_user):
        # password_option prompts twice (entry + confirmation)
        result = self._run(app, [], input="promptedpw\npromptedpw\n")

        assert result.exit_code == 0
        user = User.query.filter_by(username="testadmin").first()
        assert user.check_password("promptedpw")

    def test_mismatched_confirmation_does_not_update(self, app, admin_user):
        # click keeps re-prompting on mismatch; feed one mismatch then abort via EOF
        result = self._run(app, [], input="one\ntwo\n")

        assert result.exit_code != 0
        user = User.query.filter_by(username="testadmin").first()
        assert user.check_password("testpassword")
