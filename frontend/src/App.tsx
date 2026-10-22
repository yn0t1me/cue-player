import { Link, Route, Routes } from 'react-router-dom';
import LibraryPage from './pages/LibraryPage';
import VideoPage from './pages/VideoPage';
import CollectionPage from './pages/CollectionPage';
import ImportBatchPage from './pages/ImportBatchPage';

export default function App() {
  return (
    <div className="app-shell">
      <header><Link className="wordmark" to="/">Context English<span aria-hidden="true">.</span></Link>
        <span className="edition">视频播放 · 表达收藏</span></header>
      <main><Routes>
        <Route path="/" element={<LibraryPage />} />
        <Route path="/collections/:id" element={<CollectionPage />} />
        <Route path="/imports/:batchId" element={<ImportBatchPage />} />
        <Route path="/videos/:id" element={<VideoPage />} />
        <Route path="/videos/:id/marks" element={<VideoPage initialTab="favorites" />} />
        <Route path="*" element={<><h1 className="detail-title">页面不存在</h1><Link className="back-link" to="/">返回视频库</Link></>} />
      </Routes></main>
      <footer><span>Context before memorization.</span><span>本地视频素材库</span></footer>
    </div>
  );
}
