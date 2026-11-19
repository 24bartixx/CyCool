import { NavLink, Outlet } from 'react-router'
import ApiStatus from './ApiStatus.tsx'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition-colors ${
    isActive ? 'text-primary' : 'text-muted hover:text-foreground'
  }`

export default function Layout() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b border-border bg-surface">
        <nav className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
          <span className="font-semibold text-primary">Hackathon App</span>
          <NavLink to="/" end className={navLinkClass}>
            Home
          </NavLink>
          <NavLink to="/places" className={navLinkClass}>
            Places
          </NavLink>
          <div className="ml-auto">
            <ApiStatus />
          </div>
        </nav>
      </header>
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
