// API types for authentication module
export interface CsrfToken {
  headerName: string;
  token: string;
}

export interface CurrentUser {
  id: number;
  username: string;
  role: 'ADMIN' | 'STAFF' | 'STUDENT';
  enabled: boolean;
  fullName?: string;
  studentCode?: string;
}

export interface ApiError {
  status: number;
  message: string;
}
