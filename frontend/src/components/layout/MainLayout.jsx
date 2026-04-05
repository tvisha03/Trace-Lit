import React from 'react';

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
  const [leftWidth, setLeftWidth] = React.useState(224);
  const [rightWidth, setRightWidth] = React.useState(274);
  const [resizing, setResizing] = React.useState(null);

  React.useEffect(() => {
    const handleMouseMove = (e) => {
      if (resizing === 'left') {
        setLeftWidth(Math.min(Math.max(e.clientX, 150), 400));
      } else if (resizing === 'right') {
        setRightWidth(Math.min(Math.max(window.innerWidth - e.clientX, 200), window.innerWidth - 300));
      }
    };
    const handleMouseUp = () => {
      setResizing(null);
    };

    if (resizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizing]);

  const leftPanelWithWidth = leftPanel ? React.cloneElement(leftPanel, { width: leftWidth }) : null;
  const rightPanelWithWidth = rightPanel ? React.cloneElement(rightPanel, { width: rightWidth }) : null;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-tl-bg select-none">
      {topbar}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        {leftPanelWithWidth}
        {leftPanel && (
          <div
            className="w-1 cursor-col-resize hover:bg-tl-gold/30 active:bg-tl-gold/50 z-10 transition-colors"
            onMouseDown={() => setResizing('left')}
          />
        )}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {mainPanel}
        </main>
        {rightPanel && (
          <div
            className="w-1 cursor-col-resize hover:bg-tl-gold/30 active:bg-tl-gold/50 z-10 transition-colors"
            onMouseDown={() => setResizing('right')}
          />
        )}
        {rightPanelWithWidth}
      </div>
    </div>
  );
}
