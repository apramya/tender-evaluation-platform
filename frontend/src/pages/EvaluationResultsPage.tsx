import React, { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, Download, FileJson, FileSearch, Loader, Mail, PlayCircle, RefreshCw, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';

const decisions = [
  { value: '', label: 'All decisions' },
  { value: 'eligible', label: 'Eligible' },
  { value: 'not_eligible', label: 'Not eligible' },
  { value: 'needs_manual_review', label: 'Needs review' },
];

const decisionStyles: Record<string, string> = {
  eligible: 'bg-green-100 text-green-800',
  not_eligible: 'bg-red-100 text-red-800',
  needs_manual_review: 'bg-amber-100 text-amber-800',
};

const formatDecision = (decision?: string) =>
  (decision || 'unknown').replace(/_/g, ' ');

const getExportErrorMessage = async (error: any, fallback: string) => {
  const data = error.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text);
      return parsed.detail || fallback;
    } catch {
      return fallback;
    }
  }
  return data?.detail || fallback;
};

const EvaluationResultsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [tenderId, setTenderId] = useState('');
  const [decision, setDecision] = useState('');
  const [selectedEvaluationId, setSelectedEvaluationId] = useState('');
  const [exportingId, setExportingId] = useState('');
  const [rerunningId, setRerunningId] = useState('');

  const { data: tendersData } = useQuery({
    queryKey: ['tenders'],
    queryFn: () => apiService.listTenders(0, 100),
  });

  const { data: biddersData } = useQuery({
    queryKey: ['bidders', tenderId],
    queryFn: () => apiService.listBidders(tenderId || undefined, 0, 100),
  });

  const {
    data: evaluationsData,
    isLoading: evaluationsLoading,
    isFetching: evaluationsFetching,
  } = useQuery({
    queryKey: ['evaluations', tenderId, decision],
    queryFn: () => apiService.listEvaluations(tenderId || undefined, decision || undefined, 0, 100),
  });

  const evaluations = evaluationsData?.evaluations || [];
  const selectedEvaluation = evaluations.find((item: any) => item.id === selectedEvaluationId) || evaluations[0];
  const tenders = tendersData?.tenders || [];
  const bidderMap = useMemo(() => {
    const map: Record<string, any> = {};
    (biddersData?.bidders || []).forEach((bidder: any) => {
      map[bidder.id] = bidder;
    });
    return map;
  }, [biddersData]);

  const handleRefresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['evaluations'] });
    toast.success('Evaluations refreshed');
  };

  const handleRerun = async (evaluation: any) => {
    try {
      setRerunningId(evaluation.id);
      await apiService.createEvaluation(evaluation.tender_id, evaluation.bidder_id);
      await queryClient.invalidateQueries({ queryKey: ['evaluations'] });
      toast.success('Evaluation re-run started');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Evaluation re-run failed');
    } finally {
      setRerunningId('');
    }
  };

  const handleExportJSON = async (evaluationId: string) => {
    try {
      setExportingId(evaluationId);
      const data = await apiService.exportEvaluationJSON(evaluationId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `evaluation_${evaluationId}_${Date.now()}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error: any) {
      toast.error(await getExportErrorMessage(error, 'JSON export failed'));
    } finally {
      setExportingId('');
    }
  };

  const handleExportPDF = async (evaluationId: string) => {
    try {
      setExportingId(evaluationId);
      const data = await apiService.exportEvaluationPDF(evaluationId);
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `evaluation_${evaluationId}_${Date.now()}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error: any) {
      toast.error(await getExportErrorMessage(error, 'PDF export failed'));
    } finally {
      setExportingId('');
    }
  };

  const handleEmailPDF = async (evaluationId: string) => {
    const input = window.prompt('Send report to email address(es), comma separated:');
    if (!input) {
      return;
    }
    const recipients = input
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    if (recipients.length === 0) {
      toast.error('Enter at least one email address');
      return;
    }

    try {
      setExportingId(evaluationId);
      await apiService.emailEvaluationPDF(evaluationId, { recipients });
      toast.success('Report email sent');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Report email failed');
    } finally {
      setExportingId('');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Evaluation Results</h1>
            <p className="text-gray-600 mt-2">Review generated evaluations and export reports.</p>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
            disabled={evaluationsFetching}
          >
            <RefreshCw size={18} className={evaluationsFetching ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        <div className="bg-white rounded-lg shadow-md p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label htmlFor="tender-filter" className="block text-sm font-medium text-gray-700 mb-1">
                Tender
              </label>
              <select
                id="tender-filter"
                value={tenderId}
                onChange={(e) => {
                  setTenderId(e.target.value);
                  setSelectedEvaluationId('');
                }}
                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                <option value="">All tenders</option>
                {tenders.map((tender: any) => (
                  <option key={tender.id} value={tender.id}>
                    {tender.title || tender.file_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="decision-filter" className="block text-sm font-medium text-gray-700 mb-1">
                Decision
              </label>
              <select
                id="decision-filter"
                value={decision}
                onChange={(e) => {
                  setDecision(e.target.value);
                  setSelectedEvaluationId('');
                }}
                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                {decisions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              <div className="w-full rounded-lg bg-gray-50 border border-gray-200 px-4 py-2">
                <p className="text-sm text-gray-500">Total results</p>
                <p className="text-2xl font-bold text-gray-900">{evaluationsData?.total || 0}</p>
              </div>
            </div>
          </div>
        </div>

        {evaluationsLoading ? (
          <div className="bg-white rounded-lg shadow-md p-10 flex items-center justify-center gap-3 text-gray-600">
            <Loader className="animate-spin" size={22} />
            Loading evaluations...
          </div>
        ) : evaluations.length === 0 ? (
          <div className="bg-white rounded-lg shadow-md p-10 text-center">
            <Search size={42} className="text-gray-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">No evaluations found</h2>
            <p className="text-gray-600 mt-1">Submit a bidder proposal and create an evaluation to see results here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <div className="xl:col-span-1 bg-white rounded-lg shadow-md divide-y divide-gray-200 overflow-hidden">
              {evaluations.map((evaluation: any) => {
                const bidder = bidderMap[evaluation.bidder_id];
                const active = selectedEvaluation?.id === evaluation.id;
                return (
                  <button
                    key={evaluation.id}
                    type="button"
                    onClick={() => setSelectedEvaluationId(evaluation.id)}
                    className={`w-full text-left p-4 hover:bg-gray-50 transition ${active ? 'bg-blue-50' : 'bg-white'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900 truncate">
                          {bidder?.company_name || evaluation.bidder_id}
                        </p>
                        <p className="text-xs text-gray-500 truncate">{evaluation.id}</p>
                      </div>
                      <span
                        className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium capitalize ${
                          decisionStyles[evaluation.overall_decision] || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {formatDecision(evaluation.overall_decision)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="xl:col-span-2 bg-white rounded-lg shadow-md p-4 sm:p-6">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 border-b border-gray-200 pb-5">
                <div>
                  <div className="flex items-center gap-3">
                    <CheckCircle className="text-blue-600" size={28} />
                    <h2 className="text-xl font-bold text-gray-900">
                      {bidderMap[selectedEvaluation.bidder_id]?.company_name || 'Evaluation detail'}
                    </h2>
                  </div>
                  <p className="text-sm text-gray-500 mt-2">{selectedEvaluation.id}</p>
                </div>
                <div className="grid grid-cols-1 sm:flex gap-2">
                  <button
                    type="button"
                    onClick={() => handleRerun(selectedEvaluation)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    disabled={rerunningId === selectedEvaluation.id}
                  >
                    {rerunningId === selectedEvaluation.id ? (
                      <Loader size={16} className="animate-spin" />
                    ) : (
                      <PlayCircle size={16} />
                    )}
                    Re-run AI
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExportJSON(selectedEvaluation.id)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    disabled={exportingId === selectedEvaluation.id}
                  >
                    <FileJson size={16} />
                    JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExportPDF(selectedEvaluation.id)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    disabled={exportingId === selectedEvaluation.id}
                  >
                    <Download size={16} />
                    PDF
                  </button>
                  <button
                    type="button"
                    onClick={() => handleEmailPDF(selectedEvaluation.id)}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    disabled={exportingId === selectedEvaluation.id}
                  >
                    <Mail size={16} />
                    Email
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 py-5">
                <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
                  <p className="text-sm text-gray-500">Decision</p>
                  <p className="font-semibold text-gray-900 capitalize">
                    {formatDecision(selectedEvaluation.overall_decision)}
                  </p>
                </div>
                <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
                  <p className="text-sm text-gray-500">Confidence</p>
                  <p className="font-semibold text-gray-900">
                    {Math.round((selectedEvaluation.overall_confidence || 0) * 100)}%
                  </p>
                </div>
                <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
                  <p className="text-sm text-gray-500">Method</p>
                  <p className="font-semibold text-gray-900 uppercase">
                    {selectedEvaluation.evaluation_method || 'AI'}
                  </p>
                </div>
              </div>

              {selectedEvaluation.decision_summary ? (
                <div className="rounded-lg border border-gray-200 p-4 mb-5">
                  <h3 className="font-semibold text-gray-900 mb-2">Summary</h3>
                  <p className="text-gray-700">{selectedEvaluation.decision_summary}</p>
                </div>
              ) : (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 mb-5">
                  <p className="text-sm text-amber-800">
                    This evaluation exists, but the backend has not populated criteria results yet.
                  </p>
                </div>
              )}

              <div>
                <h3 className="font-semibold text-gray-900 mb-3">Criteria Results</h3>
                {selectedEvaluation.criteria_results?.length > 0 ? (
                  <div className="space-y-3">
                    {selectedEvaluation.criteria_results.map((criterion: any, index: number) => (
                      <div key={`${criterion.criterion}-${index}`} className="rounded-lg border border-gray-200 p-4">
                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                          <p className="font-medium text-gray-900 break-words">{criterion.criterion}</p>
                          <span className="shrink-0 self-start rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                            {criterion.decision}
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 mt-2">{criterion.reasoning}</p>
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
                            <p className="text-xs font-medium uppercase text-gray-500">Value</p>
                            <p className="mt-1 text-gray-800 break-words">{criterion.extracted_value || 'Not found'}</p>
                          </div>
                          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
                            <p className="text-xs font-medium uppercase text-gray-500">Source</p>
                            <p className="mt-1 text-gray-800 break-words">
                              {criterion.source_document || 'Not identified'}
                              {criterion.source_page ? `, page ${criterion.source_page}` : ''}
                            </p>
                          </div>
                          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3">
                            <p className="text-xs font-medium uppercase text-gray-500">Confidence</p>
                            <p className="mt-1 text-gray-800">{Math.round((criterion.confidence || 0) * 100)}%</p>
                          </div>
                        </div>
                        {criterion.evidence_snippet && (
                          <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50 p-3">
                            <div className="flex items-center gap-2 text-xs font-medium uppercase text-blue-700">
                              <FileSearch size={14} />
                              Evidence
                            </div>
                            <p className="mt-2 text-sm text-blue-950 break-words">{criterion.evidence_snippet}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500">No criterion-level results are available yet.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default EvaluationResultsPage;
