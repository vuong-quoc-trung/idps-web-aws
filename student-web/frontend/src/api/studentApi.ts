/**
 * Student management API — CRUD for students and sub-resources.
 */
import { apiGet, apiPost, apiPut, apiDelete, type Page } from './client';
import type {
  StudentSummary, StudentDetail, CompletionStatus,
  CreateStudentPayload, CreateStudentResponse, UpdateStudentPayload,
  StudentListParams,
  Address, AddressPayload,
  FamilyMember, FamilyMemberPayload,
  EmergencyContact, EmergencyContactPayload,
  PostGradContact, PostGradContactPayload,
} from '../types/student';

const PAGE_SIZE = 20;

// ============================================================
// Students
// ============================================================
export const studentApi = {
  list: (params: StudentListParams = {}) => {
    const p: Record<string, string | number> = {
      page: params.page ?? 0,
      size: params.size ?? PAGE_SIZE,
    };
    if (params.search)  p.search  = params.search;
    if (params.majorId) p.majorId = params.majorId;
    if (params.classId) p.classId = params.classId;
    if (params.status)  p.status  = params.status;
    return apiGet<Page<StudentSummary>>('/students', p);
  },

  get: (id: number) =>
    apiGet<StudentDetail>(`/students/${id}`),

  create: (payload: CreateStudentPayload) =>
    apiPost<CreateStudentResponse>('/students', payload),

  update: (id: number, payload: UpdateStudentPayload) =>
    apiPut<StudentDetail>(`/students/${id}`, payload),

  /** Soft-delete: sets status=INACTIVE, locks account */
  deactivate: (id: number) =>
    apiDelete(`/students/${id}`),

  completion: (id: number) =>
    apiGet<CompletionStatus>(`/students/${id}/completion`),
};

// ============================================================
// Sub-resources — addresses
// ============================================================
export const addressApi = {
  list: (studentId: number) =>
    apiGet<Address[]>(`/students/${studentId}/addresses`),
  create: (studentId: number, p: AddressPayload) =>
    apiPost<Address>(`/students/${studentId}/addresses`, p),
  update: (studentId: number, id: number, p: AddressPayload) =>
    apiPut<Address>(`/students/${studentId}/addresses/${id}`, p),
  remove: (studentId: number, id: number) =>
    apiDelete(`/students/${studentId}/addresses/${id}`),
};

// ============================================================
// Sub-resources — family members
// ============================================================
export const familyApi = {
  list: (studentId: number) =>
    apiGet<FamilyMember[]>(`/students/${studentId}/family-members`),
  create: (studentId: number, p: FamilyMemberPayload) =>
    apiPost<FamilyMember>(`/students/${studentId}/family-members`, p),
  update: (studentId: number, id: number, p: FamilyMemberPayload) =>
    apiPut<FamilyMember>(`/students/${studentId}/family-members/${id}`, p),
  remove: (studentId: number, id: number) =>
    apiDelete(`/students/${studentId}/family-members/${id}`),
};

// ============================================================
// Sub-resources — emergency contacts
// ============================================================
export const emergencyApi = {
  list: (studentId: number) =>
    apiGet<EmergencyContact[]>(`/students/${studentId}/emergency-contacts`),
  create: (studentId: number, p: EmergencyContactPayload) =>
    apiPost<EmergencyContact>(`/students/${studentId}/emergency-contacts`, p),
  update: (studentId: number, id: number, p: EmergencyContactPayload) =>
    apiPut<EmergencyContact>(`/students/${studentId}/emergency-contacts/${id}`, p),
  remove: (studentId: number, id: number) =>
    apiDelete(`/students/${studentId}/emergency-contacts/${id}`),
};

// ============================================================
// Sub-resources — post-graduation contacts
// ============================================================
export const postGradApi = {
  list: (studentId: number) =>
    apiGet<PostGradContact[]>(`/students/${studentId}/post-graduation-contacts`),
  create: (studentId: number, p: PostGradContactPayload) =>
    apiPost<PostGradContact>(`/students/${studentId}/post-graduation-contacts`, p),
  update: (studentId: number, id: number, p: PostGradContactPayload) =>
    apiPut<PostGradContact>(`/students/${studentId}/post-graduation-contacts/${id}`, p),
  remove: (studentId: number, id: number) =>
    apiDelete(`/students/${studentId}/post-graduation-contacts/${id}`),
};
