import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './shell.component.html',
})
export class ShellComponent implements OnInit {
  open: Record<string, boolean> = {
    gl: true,
    banking: false,
    reports: false,
    payables: false,
    receivables: false,
    budget: false,
    admin: false,
  };

  companyControlLabel = 'Switch Company';

  constructor(public auth: AuthService, private router: Router) {}

  async ngOnInit() {
    try {
      const memberships = await this.auth.getMemberships();
      // Always show the control — it's also the only way to *add* a company, which
      // matters most for the common single-membership case. Label reflects intent:
      // switching only makes sense once there's something else to switch to.
      this.companyControlLabel = memberships.length > 1 ? 'Switch Company' : 'Add Company';
    } catch {
      this.companyControlLabel = 'Switch Company';
    }
  }

  get companyName(): string {
    return this.auth.getCurrentUser()?.companyName ?? 'Page';
  }

  toggle(section: string) {
    this.open[section] = !this.open[section];
  }

  logout() { this.auth.logout(); this.router.navigate(['/login']); }

  switchCompany() { this.router.navigate(['/select-company']); }

  get isAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return !!user && user.roles.includes('Admin');
  }
}
