import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, History, Loader } from 'lucide-react';
import apiService from '../services/apiService';

const AuditLogsPage: React.FC = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => apiService.listAuditLogs(0, 100),
  });

  const logs = data?.logs || [];

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-600 mt-2">Track platform actions, statuses, and errors.</p>
        </div>

        {isLoading ? (
          <div className="bg-white rounded-lg shadow-md p-10 flex items-center justify-center gap-3 text-gray-600">
            <Loader className="animate-spin" size={22} />
            Loading audit logs...
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow-md p-8 flex gap-3 text-red-700">
            <AlertCircle size={22} className="shrink-0" />
            <p>Unable to load audit logs. This page requires admin access.</p>
          </div>
        ) : logs.length === 0 ? (
          <div className="bg-white rounded-lg shadow-md p-10 text-center">
            <History size={44} className="text-gray-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">No audit logs yet</h2>
            <p className="text-gray-600 mt-1">Actions recorded by the backend will appear here.</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Time</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Action</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Entity</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {logs.map((log: any) => (
                    <tr key={log.id}>
                      <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{log.action}</td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {log.entity_type}
                        {log.entity_id ? ` / ${log.entity_id}` : ''}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
                          {log.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-md truncate">
                        {log.error_message || (log.details ? JSON.stringify(log.details) : '-')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuditLogsPage;
