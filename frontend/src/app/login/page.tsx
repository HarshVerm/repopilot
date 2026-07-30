// Module purpose: Render the login application route.

import { Suspense } from "react";
import { LoginView } from "@/components/auth/login-view";

/** Purpose: Render the login page interface. */
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginView />
    </Suspense>
  );
}
