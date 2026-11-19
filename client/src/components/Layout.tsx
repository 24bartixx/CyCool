import { Outlet } from 'react-router'

/** Full-height shell; the planner page renders its own header. */
export default function Layout() {
  return (
    <div className="flex h-svh min-h-0 flex-col">
      <Outlet />
    </div>
  )
}
