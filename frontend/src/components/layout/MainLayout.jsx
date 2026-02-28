/** TraceLit — Main Layout with resizable split pane */
import { useState, useRef, useCallback } from 'react';
import Header from './Header';
import Sidebar from './Sidebar';

export default function MainLayout({ sourcePanel, chatPanel }) {
  const [splitPercent, setSplitPercent] = useState(40);
  const containerRef = useRef(null);
  const isDragging = useRef(false);

  const onMouseDown = useCallback((e) => {
    isDragging.current = true;
    e.preventDefault();
  }, []);

  const onMouseMove = useCallback((e) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = Math.min(Math.max(((e.clientX - rect.left) / rect.width) * 100, 20), 75);
    setSplitPercent(pct);
  }, []);

  const onMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  return (
    <div
      className="flex h-screen bg-slate-50 select-none overflow-hidden"
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
    >
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header />
        <div className="flex flex-1 min-h-0 overflow-hidden" ref={containerRef}>
          {/* Source panel */}
          <div
            style={{ width: `${splitPercent}%` }}
            className="flex flex-col min-w-0 overflow-hidden"
          >
            {sourcePanel}
          </div>
          {/* Resize handle */}
          <div
            className="w-1 bg-slate-200 hover:bg-blue-400 active:bg-blue-500 cursor-col-resize flex-shrink-0 transition-colors"
            onMouseDown={onMouseDown}
          />
          {/* Chat panel */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {chatPanel}
          </div>
        </div>
      </div>
    </div>
  );
}
