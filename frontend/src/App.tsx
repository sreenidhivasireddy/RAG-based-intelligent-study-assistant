import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import KnowledgeBase from './pages/KnowledgeBase';
import Chat from './pages/Chat';
import Quiz from './pages/Quiz';
import Evaluation from './pages/Evaluation';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="files" element={<KnowledgeBase />} />
          <Route path="quiz" element={<Quiz />} />
          <Route path="evaluation" element={<Evaluation />} />
          <Route path="chat" element={<Chat />} />
          <Route path="chat/:conversationId" element={<Chat />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;

