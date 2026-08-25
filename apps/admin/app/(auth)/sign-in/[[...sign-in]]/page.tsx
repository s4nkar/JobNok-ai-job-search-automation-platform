import { SignIn } from '@clerk/nextjs'

// Clerk's own prebuilt component - no custom form needed for an internal
// tool with no self-serve signup (admins are provisioned directly in Clerk).
export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <SignIn />
    </div>
  )
}
