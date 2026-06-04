import axios, { AxiosInstance } from 'axios';
import { useAuthStore } from '../store/authStore';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

class APIService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add request interceptor to include token
    this.client.interceptors.request.use((config) => {
      const token = useAuthStore.getState().token;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Add response interceptor to handle auth errors
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        const requestUrl = error.config?.url || '';
        const isAuthRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/signup');
        if (error.response?.status === 401 && !isAuthRequest) {
          useAuthStore.getState().logout();
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // Auth endpoints
  async login(email: string, password: string) {
    const response = await this.client.post('/auth/login', { email, password });
    return response.data;
  }

  async signup(email: string, password: string, full_name: string, organization?: string) {
    const response = await this.client.post('/auth/signup', {
      email,
      password,
      full_name,
      organization,
    });
    return response.data;
  }

  async requestSignupOtp(email: string, password: string, full_name: string, organization?: string) {
    const response = await this.client.post('/auth/signup/request-otp', {
      email,
      password,
      full_name,
      organization,
    });
    return response.data;
  }

  async verifySignupOtp(email: string, otp: string) {
    const response = await this.client.post('/auth/signup/verify', { email, otp });
    return response.data;
  }

  getOAuthStartUrl(provider: 'google' | 'linkedin') {
    return `${API_URL}/auth/oauth/${provider}/start`;
  }

  async getCurrentUser() {
    const response = await this.client.get('/auth/me');
    return response.data;
  }

  async listUsers(skip = 0, limit = 100) {
    const response = await this.client.get('/auth/users', { params: { skip, limit } });
    return response.data;
  }

  async createUser(user_data: any) {
    const response = await this.client.post('/auth/users', user_data);
    return response.data;
  }

  async updateUser(user_id: string, update_data: any) {
    const response = await this.client.patch(`/auth/users/${user_id}`, update_data);
    return response.data;
  }

  async deleteUser(user_id: string) {
    const response = await this.client.delete(`/auth/users/${user_id}`);
    return response.data;
  }

  // Tender endpoints
  async uploadTender(file: File, tender_data: any) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('tender_data', JSON.stringify(tender_data));

    const response = await this.client.post('/tenders/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async getTender(tender_id: string) {
    const response = await this.client.get(`/tenders/${tender_id}`);
    return response.data;
  }

  async listTenders(skip = 0, limit = 10) {
    const response = await this.client.get('/tenders', { params: { skip, limit } });
    return response.data;
  }

  async deleteTender(tender_id: string) {
    const response = await this.client.delete(`/tenders/${tender_id}`);
    return response.data;
  }

  // Bidder endpoints
  async createBidder(bidder_data: any) {
    const response = await this.client.post('/bidders', bidder_data);
    return response.data;
  }

  async uploadBidderDocument(bidder_id: string, file: File, document_type: string) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', document_type);

    const response = await this.client.post(
      `/bidders/${bidder_id}/upload-document`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  }

  async getBidder(bidder_id: string) {
    const response = await this.client.get(`/bidders/${bidder_id}`);
    return response.data;
  }

  async listBidders(tender_id?: string, skip = 0, limit = 10) {
    const response = await this.client.get('/bidders', {
      params: { tender_id, skip, limit },
    });
    return response.data;
  }

  async deleteBidder(bidder_id: string) {
    const response = await this.client.delete(`/bidders/${bidder_id}`);
    return response.data;
  }

  async deleteBidderDocument(bidder_id: string, document_id: string) {
    const response = await this.client.delete(`/bidders/${bidder_id}/documents/${document_id}`);
    return response.data;
  }

  // Evaluation endpoints
  async createEvaluation(tender_id: string, bidder_id: string) {
    const response = await this.client.post('/evaluations', { tender_id, bidder_id });
    return response.data;
  }

  async getEvaluation(evaluation_id: string) {
    const response = await this.client.get(`/evaluations/${evaluation_id}`);
    return response.data;
  }

  async listEvaluations(tender_id?: string, decision?: string, skip = 0, limit = 10) {
    const response = await this.client.get('/evaluations', {
      params: { tender_id, decision, skip, limit },
    });
    return response.data;
  }

  async overrideEvaluation(evaluation_id: string, new_decision: string, comments: string) {
    const response = await this.client.post(`/evaluations/${evaluation_id}/override`, {
      new_decision,
      comments,
    });
    return response.data;
  }

  // Review endpoints
  async getReviewQueue(skip = 0, limit = 20) {
    const response = await this.client.get('/review/queue', { params: { skip, limit } });
    return response.data;
  }

  async listReviewAssignees() {
    const response = await this.client.get('/review/assignees');
    return response.data;
  }

  async assignReviewToMe(review_queue_id: string) {
    const response = await this.client.post(`/review/${review_queue_id}/assign-to-me`);
    return response.data;
  }

  async assignReview(review_queue_id: string, user_id: string) {
    const response = await this.client.post(`/review/${review_queue_id}/assign`, { user_id });
    return response.data;
  }

  async submitReview(evaluation_id: string, decision: string, comments: string, approved: boolean) {
    const response = await this.client.post('/review', {
      evaluation_id,
      decision,
      comments,
      approved,
    });
    return response.data;
  }

  // Audit endpoints
  async listAuditLogs(skip = 0, limit = 50) {
    const response = await this.client.get('/audit', { params: { skip, limit } });
    return response.data;
  }

  async getTenderAuditLogs(tender_id: string) {
    const response = await this.client.get(`/audit/tender/${tender_id}`);
    return response.data;
  }

  // Export endpoints
  async exportEvaluationPDF(evaluation_id: string) {
    const response = await this.client.get(`/export/evaluation/${evaluation_id}/pdf`, {
      responseType: 'blob',
    });
    return response.data;
  }

  async emailEvaluationPDF(evaluation_id: string, payload: {
    recipients: string[];
    cc?: string[];
    subject?: string;
    message?: string;
  }) {
    const response = await this.client.post(`/export/evaluation/${evaluation_id}/email`, payload);
    return response.data;
  }

  async exportEvaluationJSON(evaluation_id: string) {
    const response = await this.client.get(`/export/evaluation/${evaluation_id}/json`);
    return response.data;
  }

  async exportTenderComparison(tender_id: string) {
    const response = await this.client.get(`/export/tender/${tender_id}/comparison`);
    return response.data;
  }
}

const apiService = new APIService();

export default apiService;
