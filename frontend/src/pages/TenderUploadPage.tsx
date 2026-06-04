import React, { useState } from 'react';
import { Upload, Loader } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import apiService from '../services/apiService';

const TenderUploadPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!file) {
      toast.error('Please select a file');
      return;
    }

    try {
      setLoading(true);
      await apiService.uploadTender(file, {});
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tenders'] }),
        queryClient.invalidateQueries({ queryKey: ['evaluations'] }),
      ]);
      toast.success('Tender uploaded successfully!');
      setFile(null);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-6 sm:py-8">
      <div className="max-w-2xl mx-auto px-3 sm:px-4">
        <h1 className="text-2xl sm:text-4xl font-bold text-gray-900 mb-6 sm:mb-8">Upload Tender Document</h1>
        
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-md p-4 sm:p-8">
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-5 sm:p-8 text-center">
            <Upload className="mx-auto text-gray-400 mb-4" size={40} />
            <input
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.docx,.doc"
              className="hidden"
              id="file-input"
            />
            <label htmlFor="file-input" className="cursor-pointer">
              <p className="text-base sm:text-lg font-medium text-gray-900 break-words">
                {file ? file.name : 'Click to upload or drag and drop'}
              </p>
              <p className="text-sm text-gray-500">PDF, DOCX or DOC</p>
            </label>
          </div>

          <button
            type="submit"
            disabled={loading || !file}
            className="mt-6 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center space-x-2"
          >
            {loading && <Loader size={20} className="animate-spin" />}
            <span>{loading ? 'Uploading...' : 'Upload Tender'}</span>
          </button>
          {loading && (
            <p className="mt-3 text-center text-sm text-gray-500">
              Saving the file. Text extraction and AI processing continue after upload.
            </p>
          )}
        </form>
      </div>
    </div>
  );
};

export default TenderUploadPage;
