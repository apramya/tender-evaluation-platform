import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, FileText, Loader, Trash2, Upload } from 'lucide-react';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';
import { useAuthStore } from '../store/authStore';

const TenderManagementPage: React.FC = () => {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const [expandedTenderId, setExpandedTenderId] = useState('');
  const canDeleteTenders = user?.role === 'admin';

  const { data, isLoading, error } = useQuery({
    queryKey: ['tenders'],
    queryFn: () => apiService.listTenders(0, 100),
  });

  const tenders = data?.tenders || [];

  const handleDeleteTender = async (tenderId: string) => {
    if (!window.confirm('Delete this tender and all related bidders, documents, evaluations and reviews?')) {
      return;
    }

    try {
      await apiService.deleteTender(tenderId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tenders'] }),
        queryClient.invalidateQueries({ queryKey: ['bidders'] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
      ]);
      toast.success('Tender deleted');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Could not delete tender');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-6 sm:py-8">
      <div className="max-w-7xl mx-auto px-3 sm:px-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Tender Management</h1>
            <p className="text-gray-600 mt-2">Upload official tenders and manage tender records.</p>
          </div>
          <Link
            to="/tender/upload"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700"
          >
            <Upload size={18} />
            Upload Tender
          </Link>
        </div>

        {isLoading ? (
          <div className="bg-white rounded-lg shadow-md p-10 flex items-center justify-center gap-3 text-gray-600">
            <Loader className="animate-spin" size={22} />
            Loading tenders...
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow-md p-8 text-red-700">
            Could not load tenders.
          </div>
        ) : tenders.length === 0 ? (
          <div className="bg-white rounded-lg shadow-md p-10 text-center">
            <FileText size={42} className="text-gray-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">No tenders uploaded</h2>
            <p className="text-gray-600 mt-1">Upload the first tender before bidder submissions are collected.</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="hidden md:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Tender</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">File</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Status</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {tenders.map((tender: any) => (
                    <React.Fragment key={tender.id}>
                      <tr>
                        <td className="px-4 py-3">
                          <div className="flex items-start gap-2">
                            <button
                              type="button"
                              onClick={() => setExpandedTenderId(expandedTenderId === tender.id ? '' : tender.id)}
                              className="mt-1 inline-flex text-gray-500 hover:text-gray-900"
                              aria-label="Toggle extracted criteria"
                            >
                              {expandedTenderId === tender.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <div>
                              <p className="font-medium text-gray-900">{tender.title || tender.file_name}</p>
                              <p className="text-sm text-gray-500">{tender.tender_number}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">{tender.file_name}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                            {tender.extraction_status || 'pending'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {canDeleteTenders && (
                            <button
                              type="button"
                              onClick={() => handleDeleteTender(tender.id)}
                              className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                            >
                              <Trash2 size={16} />
                              Delete
                            </button>
                          )}
                        </td>
                      </tr>
                      {expandedTenderId === tender.id && (
                        <tr>
                          <td colSpan={4} className="bg-gray-50 px-4 py-4">
                            <CriteriaPanel tender={tender} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="md:hidden divide-y divide-gray-200">
              {tenders.map((tender: any) => (
                <div key={tender.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <button
                        type="button"
                        onClick={() => setExpandedTenderId(expandedTenderId === tender.id ? '' : tender.id)}
                        className="flex items-center gap-1 font-medium text-gray-900"
                      >
                        {expandedTenderId === tender.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <span className="truncate">{tender.title || tender.file_name}</span>
                      </button>
                      <p className="text-sm text-gray-500 truncate">{tender.tender_number}</p>
                      <p className="text-xs text-gray-500 mt-1 truncate">{tender.file_name}</p>
                    </div>
                    <span className="shrink-0 rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                      {tender.extraction_status || 'pending'}
                    </span>
                  </div>
                  {canDeleteTenders && (
                    <button
                      type="button"
                      onClick={() => handleDeleteTender(tender.id)}
                      className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      <Trash2 size={16} />
                      Delete Tender
                    </button>
                  )}
                  {expandedTenderId === tender.id && (
                    <div className="mt-4">
                      <CriteriaPanel tender={tender} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const CriteriaPanel: React.FC<{ tender: any }> = ({ tender }) => {
  const criteria = tender.criteria || [];
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900">Extracted Criteria</h3>
      {criteria.length === 0 ? (
        <p className="mt-2 text-sm text-gray-600">
          Criteria have not been extracted yet. Run processing/evaluation after OCR completes.
        </p>
      ) : (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
          {criteria.map((criterion: any) => (
            <div key={criterion.id || criterion.criterion_id} className="rounded-lg border border-gray-200 bg-white p-3">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                <p className="font-medium text-gray-900 break-words">{criterion.description}</p>
                <span className="shrink-0 self-start rounded-full bg-gray-100 px-2 py-1 text-xs font-medium capitalize text-gray-700">
                  {criterion.criterion_type || criterion.type || 'criterion'}
                </span>
              </div>
              <div className="mt-2 text-sm text-gray-600">
                {criterion.operator && criterion.value ? (
                  <p>
                    Rule: {criterion.operator} {criterion.value} {criterion.unit || ''}
                  </p>
                ) : (
                  <p>Rule: evidence required</p>
                )}
                <p>Mandatory: {criterion.is_mandatory === false ? 'No' : 'Yes'}</p>
                {criterion.source_page && <p>Source page: {criterion.source_page}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TenderManagementPage;
