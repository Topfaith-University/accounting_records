import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService, Membership } from '../../services/auth.service';

@Component({
  selector: 'app-company-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './company-select.component.html',
})
export class CompanySelectComponent implements OnInit {
  memberships: Membership[] = [];
  loading = true;
  switching = false;
  error = '';

  showAddForm = false;
  addMode: 'join' | 'create' = 'join';
  inviteCode = '';
  companyName = '';
  adding = false;
  addError = '';

  constructor(private auth: AuthService, private router: Router) {}

  async ngOnInit() {
    try {
      // No auto-select here, even if there's exactly one membership: this screen
      // is now also the entry point for "Add Company" on the sidebar (the only
      // way a single-membership user can reach it), so it must actually render
      // instead of bouncing straight back to /accounts.
      await this.refreshMemberships();
    } catch {
      this.error = 'Failed to load your companies.';
    } finally {
      this.loading = false;
    }
  }

  private async refreshMemberships() {
    this.memberships = await this.auth.getMemberships();
    this.error = this.memberships.length === 0
      ? 'Your account is not linked to any company yet. Join one with an invite code, or create your own below.'
      : '';
  }

  async select(membership: Membership) {
    this.switching = true;
    this.error = '';
    try {
      await this.auth.switchCompany(membership.company_id);
      this.router.navigate(['/accounts']);
    } catch {
      this.error = 'Failed to switch company. Please try again.';
      this.switching = false;
    }
  }

  toggleAddForm() {
    this.showAddForm = !this.showAddForm;
    this.addError = '';
    this.inviteCode = '';
    this.companyName = '';
  }

  setAddMode(mode: 'join' | 'create') {
    this.addMode = mode;
    this.addError = '';
  }

  async submitAdd() {
    this.addError = '';
    this.adding = true;
    try {
      if (this.addMode === 'join') {
        await this.auth.joinCompany(this.inviteCode);
      } else {
        await this.auth.createCompanyForCurrentUser(this.companyName);
      }
      this.showAddForm = false;
      await this.refreshMemberships();
      if (this.memberships.length === 1) {
        // This was the user's first-ever company (0 -> 1) — take them straight in
        // rather than making them click their own newly-added company to enter it.
        await this.select(this.memberships[0]);
      }
    } catch (e: any) {
      this.addError = e.response?.data?.detail ?? 'Failed. Please try again.';
    } finally {
      this.adding = false;
    }
  }

  logout() {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
