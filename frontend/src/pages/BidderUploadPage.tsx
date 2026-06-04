import React, { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Loader, Plus, PlayCircle, Trash2, Upload, Users } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';

const documentTypes = [
  'proposal',
  'financial_statement',
  'technical_document',
  'registration_certificate',
  'tax_document',
  'other',
];

interface SubmissionFile {
  file: File;
  documentType: string;
}

interface BidderSubmission {
  id: string;
  companyName: string;
  gstNumber: string;
  panNumber: string;
  contactEmail: string;
  files: SubmissionFile[];
  showOptional: boolean;
}

const emptySubmission = (): BidderSubmission => ({
  id: crypto.randomUUID(),
  companyName: '',
  gstNumber: '',
  panNumber: '',
  contactEmail: '',
  files: [],
  showOptional: false,
});

const BidderUploadPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [tenderId, setTenderId] = useState('');
  const [submissions, setSubmissions] = useState<BidderSubmission[]>([emptySubmission()]);
  const [createEvaluation, setCreateEvaluation] = useState(true);
  const [loading, setLoading] = useState(false);

  const { data: tendersData, isLoading: tendersLoading } = useQuery({
    queryKey: ['tenders'],
    queryFn: () => apiService.listTenders(0, 100),
  });

  const tenders = useMemo(() => tendersData?.tenders || [], [tendersData]);

  const { data: biddersData } = useQuery({
    queryKey: ['bidders', tenderId],
    queryFn: () => apiService.listBidders(tenderId || undefined, 0, 100),
    enabled: !!tenderId,
  });

  const bidders = biddersData?.bidders || [];

  const updateSubmission = (id: string, patch: Partial<BidderSubmission>) => {
    setSubmissions((current) =>
      current.map((submission) => (submission.id === id ? { ...submission, ...patch } : submission))
    );
  };

  const handleFileChange = (id: string, e: React.ChangeEvent<HTMLInputElement>) => {
    updateSubmission(id, {
      files: Array.from(e.target.files || []).map((file) => ({
        file,
        documentType: documentTypes[0],
      })),
    });
  };

  const updateFileType = (submissionId: string, fileIndex: number, documentType: string) => {
    setSubmissions((current) =>
      current.map((submission) => {
        if (submission.id !== submissionId) return submission;
        const files = [...submission.files];
        files[fileIndex] = { ...files[fileIndex], documentType };
        return { ...submission, files };
      })
    );
  };

  const addSubmission = () => {
    setSubmissions((current) => [...current, emptySubmission()]);
  };

  const removeSubmission = (id: string) => {
    setSubmissions((current) => (current.length === 1 ? current : current.filter((item) => item.id !== id)));
  };

  const resetForm = () => {
    setSubmissions([emptySubmission()]);
  };

  const validate = () => {
    if (!tenderId) {
      toast.error('Please select a tender');
      return false;
    }

    for (const [index, submission] of submissions.entries()) {
      const label = `Bidder ${index + 1}`;
      if (!submission.companyName.trim()) {
        toast.error(`${label}: enter company name`);
        return false;
      }
      if (submission.files.length === 0) {
        toast.error(`${label}: select at least one document`);
        return false;
      }
    }

    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const createdBidderIds: string[] = [];

    try {
      setLoading(true);

      for (const submission of submissions) {
        const bidder = await apiService.createBidder({
          tender_id: tenderId,
          company_name: submission.companyName.trim(),
          gst_number: submission.gstNumber.trim() || null,
          pan_number: submission.panNumber.trim() || null,
          contact_email: submission.contactEmail.trim() || null,
          contact_phone: null,
        });
        createdBidderIds.push(bidder.id);

        await Promise.all(
          submission.files.map((item) => apiService.uploadBidderDocument(bidder.id, item.file, item.documentType))
        );

        if (createEvaluation) {
          await apiService.createEvaluation(tenderId, bidder.id);
        }
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['bidders'] }),
        queryClient.invalidateQueries({ queryKey: ['bidders', tenderId] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
        queryClient.invalidateQueries({ queryKey: ['review-queue'] }),
      ]);

      toast.success(
        createEvaluation
          ? `${submissions.length} bidder submission(s) uploaded and evaluated`
          : `${submissions.length} bidder submission(s) uploaded`
      );
      resetForm();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Batch bidder upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteBidder = async (bidderId: string) => {
    if (!window.confirm('Delete this bidder, documents and evaluations?')) {
      return;
    }
    try {
      await apiService.deleteBidder(bidderId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['bidders'] }),
        queryClient.invalidateQueries({ queryKey: ['bidders', tenderId] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
        queryClient.invalidateQueries({ queryKey: ['review-queue'] }),
      ]);
      toast.success('Bidder deleted');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not delete bidder');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-6 sm:py-8">
      <div className="max-w-6xl mx-auto px-3 sm:px-4">
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Bidder Submissions</h1>
          <p className="text-gray-600 mt-2">
            Upload multiple bidder submissions for one tender and optionally start evaluations.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-md p-4 sm:p-6">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-4 items-end mb-6">
            <div>
              <label htmlFor="tender" className="block text-sm font-medium text-gray-700 mb-1">
                Tender
              </label>
              <select
                id="tender"
                value={tenderId}
                onChange={(e) => setTenderId(e.target.value)}
                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                disabled={tendersLoading || loading}
              >
                <option value="">Select tender</option>
                {tenders.map((tender: any) => (
                  <option key={tender.id} value={tender.id}>
                    {tender.title || tender.file_name} ({tender.tender_number})
                  </option>
                ))}
              </select>
              {!tendersLoading && tenders.length === 0 && (
                <p className="text-sm text-amber-700 mt-2">
                  Upload a tender before submitting bidder proposals.
                </p>
              )}
            </div>

            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3">
              <input
                type="checkbox"
                checked={createEvaluation}
                onChange={(e) => setCreateEvaluation(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                disabled={loading}
              />
              <span className="text-sm text-gray-700">Create evaluations</span>
            </label>
          </div>

          <div className="space-y-4">
            {submissions.map((submission, submissionIndex) => (
              <section key={submission.id} className="rounded-lg border border-gray-200 p-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                  <h2 className="font-semibold text-gray-900">Bidder {submissionIndex + 1}</h2>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => updateSubmission(submission.id, { showOptional: !submission.showOptional })}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                      disabled={loading}
                    >
                      {submission.showOptional ? 'Hide optional fields' : 'Optional identifiers'}
                    </button>
                    {submissions.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeSubmission(submission.id)}
                        className="rounded-lg border border-red-200 p-2 text-red-700 hover:bg-red-50"
                        disabled={loading}
                        title="Remove bidder"
                      >
                        <Trash2 size={17} />
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Company name
                      </label>
                      <input
                        type="text"
                        value={submission.companyName}
                        onChange={(e) => updateSubmission(submission.id, { companyName: e.target.value })}
                        className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                        placeholder="Company name from bidder proposal"
                        disabled={loading}
                      />
                    </div>

                    {submission.showOptional && (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">GST</label>
                          <input
                            type="text"
                            value={submission.gstNumber}
                            onChange={(e) => updateSubmission(submission.id, { gstNumber: e.target.value })}
                            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                            disabled={loading}
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">PAN</label>
                          <input
                            type="text"
                            value={submission.panNumber}
                            onChange={(e) => updateSubmission(submission.id, { panNumber: e.target.value })}
                            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                            disabled={loading}
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                          <input
                            type="email"
                            value={submission.contactEmail}
                            onChange={(e) => updateSubmission(submission.id, { contactEmail: e.target.value })}
                            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                            disabled={loading}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-5 text-center">
                      <Upload className="mx-auto text-gray-400 mb-2" size={34} />
                      <input
                        type="file"
                        onChange={(event) => handleFileChange(submission.id, event)}
                        accept=".pdf,.docx,.doc,.png,.jpg,.jpeg"
                        className="hidden"
                        id={`bidder-files-${submission.id}`}
                        multiple
                        disabled={loading}
                      />
                      <label htmlFor={`bidder-files-${submission.id}`} className="cursor-pointer">
                        <p className="text-sm font-medium text-gray-900">
                          {submission.files.length > 0
                            ? `${submission.files.length} file(s) selected`
                            : 'Select documents for this bidder'}
                        </p>
                        <p className="text-xs text-gray-500">PDF, DOCX, DOC, PNG, JPG or JPEG</p>
                      </label>
                    </div>

                    {submission.files.length > 0 && (
                      <div className="mt-3 rounded-lg border border-gray-200 divide-y divide-gray-200">
                        {submission.files.map((item, fileIndex) => (
                          <div
                            key={`${item.file.name}-${item.file.size}-${fileIndex}`}
                            className="grid grid-cols-1 sm:grid-cols-[1fr_190px] gap-3 p-3"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <FileText size={18} className="text-blue-600 shrink-0" />
                              <span className="text-sm text-gray-800 truncate">{item.file.name}</span>
                            </div>
                            <select
                              value={item.documentType}
                              onChange={(e) => updateFileType(submission.id, fileIndex, e.target.value)}
                              className="w-full rounded-lg border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                              disabled={loading}
                            >
                              {documentTypes.map((type) => (
                                <option key={type} value={type}>
                                  {type.replace(/_/g, ' ')}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </section>
            ))}
          </div>

          <div className="mt-5 grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-3">
            <button
              type="button"
              onClick={addSubmission}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-4 py-3 font-medium text-gray-700 hover:bg-gray-50"
              disabled={loading}
            >
              <Plus size={18} />
              Add bidder
            </button>

            <button
              type="submit"
              disabled={loading || tenders.length === 0}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? <Loader size={20} className="animate-spin" /> : <Users size={20} />}
              <span>{loading ? 'Uploading...' : `Upload ${submissions.length} bidder submission(s)`}</span>
              {!loading && createEvaluation && <PlayCircle size={18} />}
            </button>
          </div>
        </form>

        {tenderId && (
          <div className="mt-6 bg-white rounded-lg shadow-md p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Existing bidders</h2>
            {bidders.length === 0 ? (
              <p className="text-sm text-gray-500">No bidders submitted for this tender yet.</p>
            ) : (
              <div className="space-y-3">
                {bidders.map((bidder: any) => (
                  <div
                    key={bidder.id}
                    className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-gray-200 p-3"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 truncate">{bidder.company_name}</p>
                      <p className="text-xs text-gray-500 truncate">
                        {bidder.gst_number || bidder.pan_number || bidder.contact_email || bidder.id}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteBidder(bidder.id)}
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      <Trash2 size={16} />
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default BidderUploadPage;
