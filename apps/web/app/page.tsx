import { redirect } from 'next/navigation'

// Root redirects to templates — middleware handles auth gate
export default function Home() {
  redirect('/templates')
}
