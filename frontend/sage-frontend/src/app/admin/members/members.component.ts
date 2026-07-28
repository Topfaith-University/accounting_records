import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { UsersService } from '../../services/users.service';

@Component({
  selector: 'app-members',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './members.component.html',
})
export class MembersComponent implements OnInit {
  roles = ['Staff', 'Accountant', 'Manager', 'Admin'];

  members: any[] = [];
  loading = true;
  error = '';
  savingId: number | null = null;

  constructor(
    private usersService: UsersService,
    private auth: AuthService,
    private router: Router,
  ) {}

  async ngOnInit() {
    const user = this.auth.getCurrentUser();
    if (!user || !user.roles.includes('Admin')) {
      this.router.navigate(['/dashboard']);
      return;
    }
    await this.load();
  }

  async load() {
    this.loading = true;
    this.error = '';
    try {
      this.members = await this.usersService.getMembers();
    } catch {
      this.error = 'Failed to load members.';
    } finally {
      this.loading = false;
    }
  }

  get currentUsername(): string | undefined {
    return this.auth.getCurrentUser()?.username;
  }

  async changeRole(member: any, newRole: string) {
    if (newRole === member.role) return;
    const previousRole = member.role;
    this.savingId = member.membership_id;
    this.error = '';
    try {
      const updated = await this.usersService.updateMemberRole(member.membership_id, newRole);
      member.role = updated.role;
    } catch (e: any) {
      member.role = previousRole; // revert the select on failure
      this.error = e.response?.data?.detail ?? 'Failed to update role.';
    } finally {
      this.savingId = null;
    }
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  }
}
