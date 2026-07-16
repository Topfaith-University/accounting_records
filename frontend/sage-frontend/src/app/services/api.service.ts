import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

@Injectable({ providedIn: 'root' })
export class ApiService {
  baseUrl = API_ROOT;
  async getBanks() {
    const response = await axios.get(this.baseUrl + 'banks/');
    return response.data;
  }
}
