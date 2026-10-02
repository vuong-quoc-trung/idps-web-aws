/**
 * profileApi — student self-service API client
 * Interacts with /api/me endpoints protected by Spring Security (role STUDENT).
 *
 * Endpoints:
 *   GET    /api/me/profile                -> StudentDetail of authenticated student
 *   PUT    /api/me/profile                -> Update student-declared personal fields
 *   GET    /api/me/completion             -> Profile completion status & missing fields
 *   CRUD   /api/me/addresses              -> Student's own addresses
 *   CRUD   /api/me/family-members         -> Student's own family members
 *   CRUD   /api/me/emergency-contacts     -> Student's own emergency contacts
 *   CRUD   /api/me/post-graduation-contacts -> Student's own post-grad contacts
 */
import { apiGet, apiPut, apiPost, apiDelete } from './client';
import type {
  StudentDetail,
  CompletionStatus,
  UpdateStudentProfilePayload,
  Address,
  AddressPayload,
  FamilyMember,
  FamilyMemberPayload,
  EmergencyContact,
  EmergencyContactPayload,
  PostGradContact,
  PostGradContactPayload,
} from '../types/student';

// Re-export type for convenience
export type { UpdateStudentProfilePayload };

// ============================================================
// Student Profile & Completion
// ============================================================
export const myProfileApi = {
  /** GET /api/me/profile — fetch authenticated student details */
  getProfile: (): Promise<StudentDetail> =>
    apiGet<StudentDetail>('/me/profile'),

  /** PUT /api/me/profile — update student personal/demographic fields */
  updateProfile: (payload: UpdateStudentProfilePayload): Promise<CompletionStatus> =>
    apiPut<CompletionStatus>('/me/profile', payload),

  /** GET /api/me/completion — check missing completion requirements */
  getCompletion: (): Promise<CompletionStatus> =>
    apiGet<CompletionStatus>('/me/completion'),
};

// ============================================================
// Sub-resources — Addresses
// ============================================================
export const myAddressApi = {
  list: (): Promise<Address[]> =>
    apiGet<Address[]>('/me/addresses'),
  get: (id: number): Promise<Address> =>
    apiGet<Address>(`/me/addresses/${id}`),
  create: (p: AddressPayload): Promise<Address> =>
    apiPost<Address>('/me/addresses', p),
  update: (id: number, p: AddressPayload): Promise<Address> =>
    apiPut<Address>(`/me/addresses/${id}`, p),
  remove: (id: number): Promise<void> =>
    apiDelete(`/me/addresses/${id}`),
};

// ============================================================
// Sub-resources — Family members
// ============================================================
export const myFamilyApi = {
  list: (): Promise<FamilyMember[]> =>
    apiGet<FamilyMember[]>('/me/family-members'),
  get: (id: number): Promise<FamilyMember> =>
    apiGet<FamilyMember>(`/me/family-members/${id}`),
  create: (p: FamilyMemberPayload): Promise<FamilyMember> =>
    apiPost<FamilyMember>('/me/family-members', p),
  update: (id: number, p: FamilyMemberPayload): Promise<FamilyMember> =>
    apiPut<FamilyMember>(`/me/family-members/${id}`, p),
  remove: (id: number): Promise<void> =>
    apiDelete(`/me/family-members/${id}`),
};

// ============================================================
// Sub-resources — Emergency contacts
// ============================================================
export const myEmergencyApi = {
  list: (): Promise<EmergencyContact[]> =>
    apiGet<EmergencyContact[]>('/me/emergency-contacts'),
  get: (id: number): Promise<EmergencyContact> =>
    apiGet<EmergencyContact>(`/me/emergency-contacts/${id}`),
  create: (p: EmergencyContactPayload): Promise<EmergencyContact> =>
    apiPost<EmergencyContact>('/me/emergency-contacts', p),
  update: (id: number, p: EmergencyContactPayload): Promise<EmergencyContact> =>
    apiPut<EmergencyContact>(`/me/emergency-contacts/${id}`, p),
  remove: (id: number): Promise<void> =>
    apiDelete(`/me/emergency-contacts/${id}`),
};

// ============================================================
// Sub-resources — Post-graduation contacts
// ============================================================
export const myPostGradApi = {
  list: (): Promise<PostGradContact[]> =>
    apiGet<PostGradContact[]>('/me/post-graduation-contacts'),
  get: (id: number): Promise<PostGradContact> =>
    apiGet<PostGradContact>(`/me/post-graduation-contacts/${id}`),
  create: (p: PostGradContactPayload): Promise<PostGradContact> =>
    apiPost<PostGradContact>('/me/post-graduation-contacts', p),
  update: (id: number, p: PostGradContactPayload): Promise<PostGradContact> =>
    apiPut<PostGradContact>(`/me/post-graduation-contacts/${id}`, p),
  remove: (id: number): Promise<void> =>
    apiDelete(`/me/post-graduation-contacts/${id}`),
};

// ============================================================
// Legacy compatibility helpers
// ============================================================
export type SelfUpdatePayload = UpdateStudentProfilePayload;

export async function fetchMyStudent(): Promise<StudentDetail> {
  return myProfileApi.getProfile();
}

export async function updateMyProfile(
  _studentId: number,
  _current: StudentDetail,
  patch: UpdateStudentProfilePayload,
): Promise<StudentDetail> {
  await myProfileApi.updateProfile(patch);
  return myProfileApi.getProfile();
}
