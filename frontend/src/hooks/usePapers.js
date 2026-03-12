/** TraceLit — usePapers hook */
import { useEffect } from 'react';
import usePaperStore from '../stores/paperStore';

export default function usePapers() {
  const { papers, loading, error, fetchPapers, uploadPapers, deletePaper, clearError } =
    usePaperStore();

  useEffect(() => {
    fetchPapers();
  }, [fetchPapers]);

  return { papers, loading, error, uploadPapers, deletePaper, clearError };
}
