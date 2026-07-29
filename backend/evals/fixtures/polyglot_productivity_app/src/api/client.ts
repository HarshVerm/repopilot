export type TaskPayload = {
  title: string;
  dueDate?: string;
  tags?: string[];
};

export async function createTask(baseUrl: string, payload: TaskPayload) {
  const response = await fetch(`${baseUrl}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  return response.json();
}

export async function loadDashboard(baseUrl: string) {
  const tasks = fetch(`${baseUrl}/tasks`).then((response) => response.json());
  const stats = fetch(`${baseUrl}/stats`).then((response) => response.json());

  return { tasks, stats };
}
