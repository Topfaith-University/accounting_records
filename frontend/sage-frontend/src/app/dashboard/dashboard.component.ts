import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import axios from 'axios';
import { API_ROOT } from '../services/api-base';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent implements OnInit {
  data: any = null;
  loading = true;
  error = '';

  async ngOnInit() {
    try {
      const res = await axios.get(`${API_ROOT}reports/dashboard/`);
      this.data = res.data;
    } catch {
      this.error = 'Failed to load dashboard.';
    } finally {
      this.loading = false;
    }
  }
}
