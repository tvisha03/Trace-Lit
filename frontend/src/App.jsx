import MainLayout from './components/layout/MainLayout';
import ChatInterface from './components/chat/ChatInterface';
import ErrorBoundary from './components/common/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <MainLayout>
        <ChatInterface />
      </MainLayout>
    </ErrorBoundary>
  )
}

export default App
