"""Task board transitions and participant notifications."""
from tests.helpers import API, team


def test_task_assignment_blocking_and_completion_notify_participants(signup, new_client):
    owner, worker, boss, worker_emp, boss_emp = team(signup, new_client)
    created = boss.post(f"{API}/tasks", {"title": "Prepare onboarding pack", "assignee_id": worker_emp["id"],
                                         "priority": "high"})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "todo"
    assert any("New task" in n["title"] for n in worker.get(f"{API}/notifications").json()["items"])

    blocked = worker.patch(f"{API}/tasks/{task_id}", {"status": "blocked"})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["status"] == "blocked"
    assert any("Task updated" in n["title"] for n in boss.get(f"{API}/notifications").json()["items"])

    done = boss.patch(f"{API}/tasks/{task_id}", {"status": "done"})
    assert done.status_code == 200, done.text
    assert done.json()["completed_at"] is not None
    assert any("Task moved to done" in n["title"] for n in worker.get(f"{API}/notifications").json()["items"])

    reassigned = boss.patch(f"{API}/tasks/{task_id}", {"assignee_id": boss_emp["id"]})
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["assignee_id"] == boss_emp["id"]
    assert worker.patch(f"{API}/tasks/{task_id}", {"status": "todo"}).status_code == 404
