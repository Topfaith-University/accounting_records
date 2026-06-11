import { Injectable } from '@angular/core';
import axios from 'axios';

const BASE = 'http://localhost:8002/api/users/';

@Injectable({ providedIn: 'root' })
export class UsersService {
  getInviteCodes(): Promise<any[]> {
    return axios.get(BASE + 'invite-codes/').then(r => r.data);
  }

  generateInviteCode(): Promise<any> {
    return axios.post(BASE + 'invite-codes/').then(r => r.data);
  }

  revokeInviteCode(id: number): Promise<void> {
    return axios.delete(BASE + `invite-codes/${id}/`).then(() => undefined);
  }
}
