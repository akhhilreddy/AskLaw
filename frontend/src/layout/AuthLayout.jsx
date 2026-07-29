function AuthLayout({ children }) {
  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <header className="flex items-center px-8 py-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          ⚖️ AskLaw
        </h1>
      </header>

      {/* Main Content */}
      <main className="flex justify-center px-6">
        <div className="w-full max-w-md">
          {children}
        </div>
      </main>
    </div>
  );
}

export default AuthLayout;