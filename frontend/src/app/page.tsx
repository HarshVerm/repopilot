// Module purpose: Render the app application route.

import { redirect } from "next/navigation";

/** Purpose: Render the home interface. */
export default function Home() {
  redirect("/tasks");
}
