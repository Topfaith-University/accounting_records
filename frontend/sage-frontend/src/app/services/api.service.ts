import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class ApiService {
  baseUrl = 'http://localhost:8000/api/';
  async getBanks() {
    const response = await axios.get(this.baseUrl + 'banks/');
    return response.data;
  }
}
