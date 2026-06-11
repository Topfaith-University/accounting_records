import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './shell.component.html',
})
export class ShellComponent {
  open: Record<string, boolean> = {
    gl: true,
    banking: false,
    reports: false,
    payables: false,
    receivables: false,
    budget: false,
    admin: false,
  };

  constructor(public auth: AuthService, private router: Router) {}

  toggle(section: string) {
    this.open[section] = !this.open[section];
  }

  logout() { this.auth.logout(); this.router.navigate(['/login']); }

  get isAdmin(): boolean {
    const user = this.auth.getCurrentUser();
    return !!user && (user.roles.includes('Admin') || user.roles.includes('Manager'));
  }
}
