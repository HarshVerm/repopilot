export type Todo = {
  id: string;
  title: string;
  completed: boolean;
  tags: string[];
};

export type TodoState = {
  todos: Todo[];
  filter: "all" | "active" | "completed";
};

export function toggleTodo(state: TodoState, id: string): TodoState {
  const found = state.todos.find((todo) => todo.id === id);

  if (found) {
    found.completed = !found.completed;
  }

  return state;
}

export function visibleTodos(state: TodoState): Todo[] {
  if (state.filter === "active") {
    return state.todos.filter((todo) => !todo.completed);
  }

  if (state.filter === "completed") {
    return state.todos.filter((todo) => todo.completed);
  }

  return state.todos;
}
