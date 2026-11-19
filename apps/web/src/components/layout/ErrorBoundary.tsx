import { Component, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <div role="alert" className="mx-auto my-24 max-w-lg rounded-2xl border border-border bg-surface p-8 text-center"><h1 className="text-2xl font-bold">Let’s get you back to work.</h1><p className="my-4 text-muted">This page could not be displayed. Reload to try again. If you were submitting a request, check its status before submitting it again.</p><button className="cursor-pointer rounded-lg bg-primary px-5 py-2.5 font-semibold text-white" onClick={() => window.location.reload()}>Reload page</button><a href="/" className="ml-4 text-primary">Go home</a></div>
    return this.props.children
  }
}
