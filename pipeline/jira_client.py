from jira import JIRA


class JiraClient:
    def __init__(self, server: str, email: str, api_token: str):
        self._jira = JIRA(server=server, basic_auth=(email, api_token))

    def get_ticket(self, ticket_id: str) -> dict:
        issue = self._jira.issue(ticket_id)
        fields = issue.fields

        description = fields.description or ""
        acceptance_criteria = getattr(fields, "customfield_10016", None) or ""

        full_description = description
        if acceptance_criteria:
            full_description += f"\n\nAcceptance Criteria:\n{acceptance_criteria}"

        return {
            "id": ticket_id,
            "summary": fields.summary,
            "description": full_description,
            "status": fields.status.name,
            "issue_type": fields.issuetype.name,
        }

    def add_comment(self, ticket_id: str, comment: str):
        self._jira.add_comment(ticket_id, comment)

    def transition_issue(self, ticket_id: str, transition_name: str):
        transitions = self._jira.transitions(ticket_id)
        match = next(
            (t for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if match:
            self._jira.transition_issue(ticket_id, match["id"])
        else:
            available = [t["name"] for t in transitions]
            raise ValueError(
                f"Transition '{transition_name}' not found. Available: {available}"
            )
