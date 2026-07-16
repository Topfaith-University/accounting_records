import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { UsersService } from '../../services/users.service';

@Component({
  selector: 'app-invite-codes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './invite-codes.component.html',
  styleUrls: ['./invite-codes.component.css'],
})
export class InviteCodesComponent implements OnInit {
  roles = ['Staff', 'Accountant', 'Manager', 'Admin'];
  selectedRole = 'Staff';

  codes: any[] = [];
  loading = true;
  error = '';
  generating = false;
  revoking: number | null = null;
  copiedId: number | null = null;

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
      this.codes = await this.usersService.getInviteCodes();
    } catch {
      this.error = 'Failed to load invite codes.';
    } finally {
      this.loading = false;
    }
  }

  async generate() {
    this.generating = true;
    this.error = '';
    try {
      const code = await this.usersService.generateInviteCode(this.selectedRole);
      this.codes = [code, ...this.codes];
    } catch {
      this.error = 'Failed to generate code.';
    } finally {
      this.generating = false;
    }
  }

  async revoke(id: number) {
    this.revoking = id;
    this.error = '';
    try {
      await this.usersService.revokeInviteCode(id);
      this.codes = this.codes.filter(c => c.id !== id);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to revoke code.';
    } finally {
      this.revoking = null;
    }
  }

  async copy(code: any) {
    try {
      await navigator.clipboard.writeText(code.code);
      this.copiedId = code.id;
      setTimeout(() => { if (this.copiedId === code.id) this.copiedId = null; }, 2000);
    } catch {
      // Fallback: select the text manually
    }
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  }

  get activeCodes() { return this.codes.filter(c => c.status === 'active'); }
  get usedCodes()   { return this.codes.filter(c => c.status === 'used'); }
  get expiredCodes(){ return this.codes.filter(c => c.status === 'expired'); }
}
