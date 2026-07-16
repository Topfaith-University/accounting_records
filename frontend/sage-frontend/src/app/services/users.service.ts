import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

const BASE = `${API_ROOT}users/`;

@Injectable({ providedIn: 'root' })
export class UsersService {
  getInviteCodes(): Promise<any[]> {
    return axios.get(BASE + 'invite-codes/').then(r => r.data);
  }

  generateInviteCode(role: string): Promise<any> {
    return axios.post(BASE + 'invite-codes/', { role }).then(r => r.data);
  }

  revokeInviteCode(id: number): Promise<void> {
    return axios.delete(BASE + `invite-codes/${id}/`).then(() => undefined);
  }

  getMembers(): Promise<any[]> {
    return axios.get(BASE + 'members/').then(r => r.data);
  }

  updateMemberRole(membershipId: number, role: string): Promise<any> {
    return axios.patch(BASE + `members/${membershipId}/`, { role }).then(r => r.data);
  }
}
