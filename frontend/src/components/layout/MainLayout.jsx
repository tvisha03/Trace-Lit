/**
 * TraceLit — App Shell
 *
 * Structure:
 *   ┌──────────── Topbar (50px) ─────────────┐
 *   ├──────────┬──────────────┬──────────────┤
 *   │ Left     │ Main panel   │ Right panel  │
 *   │ (224px)  │ (flex-1)     │ (274px)      │
 *   └──────────┴──────────────┴──────────────┘
 *
 * Props:
 *   topbar     ReactNode
 *   leftPanel  ReactNode
 *   mainPanel  ReactNode
 *   rightPanel ReactNode
 */
export default function MainLayout({ topbar, leftPanel, mainPanel, rightPanel }) {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-tl-bg select-none">
      {/* Topbar */}
      {topbar}

      {/* Three-column body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {leftPanel}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {mainPanel}
        </main>
        {rightPanel}
      </div>
    </div>
  );
}
